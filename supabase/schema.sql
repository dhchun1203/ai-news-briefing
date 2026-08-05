-- Supabase SQL Editor에서 한 번 실행한다.
-- 이메일 구독자 원본 데이터를 저장하는 테이블. 확인(더블 옵트인) 전/후, 구독 취소 여부를
-- 모두 여기 한 곳에 누적한다 (Resend는 발송만 담당, 구독자 목록의 진실 소스는 이 테이블).

create table if not exists subscribers (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  created_at timestamptz not null default now(),
  confirmed_at timestamptz,
  unsubscribed_at timestamptz,
  -- 확인 메일을 마지막으로 보낸 시각. /api/subscribe가 이 값을 보고 쿨다운(기본 10분)
  -- 안에 재요청이 오면 메일을 보내지 않는다. 레이트 리밋이 전혀 없으면 누구나 남의
  -- 주소로 확인 메일을 무제한 발사할 수 있어(메일 폭탄 + 발신 도메인 평판 훼손),
  -- 이 컬럼이 그 유일한 방어선이다.
  last_confirm_sent_at timestamptz
);

-- 이미 테이블을 만든 뒤라면 아래로 컬럼만 추가한다 (재실행해도 안전).
alter table subscribers add column if not exists last_confirm_sent_at timestamptz;

-- 구독 시점 브라우저의 IANA 시간대(예: "America/New_York"). 지금은 **기록만** 하고
-- 발송 방식은 바꾸지 않는다.
--
-- 왜 필요한가: 발송은 08:00 KST 한 번인데 이건 미국 동부 기준 전날 19시다. 방문자
-- 국가 1위가 미국이라, 언젠가 구독자별 현지 아침에 보내는 선택을 하게 될 수 있다
-- (Resend 배치가 항목마다 다른 scheduled_at을 받으므로 새 인프라는 필요 없다).
-- 그 판단을 하려면 "구독자가 실제로 어느 시간대에 있는가"라는 데이터가 있어야 하는데,
-- 안 모으면 나중에 소급해서 얻을 방법이 없다. 기록은 되돌릴 수 있고 발송은 아니다.
--
-- IP 조회가 아니라 브라우저가 알려주는 값을 쓴다(Intl.DateTimeFormat). 외부 호출이
-- 없고, IP 추정보다 정확하며, 무인 운영 원칙과도 부딪히지 않는다.
alter table subscribers add column if not exists timezone text;

-- 서버리스 함수(Vercel)와 배포 파이프라인(scripts/send_broadcast.py)은 모두
-- service_role 키로 접근하므로 RLS 정책을 별도로 만들 필요는 없지만, anon/public 키로는
-- 아무 것도 접근하지 못하도록 RLS를 켜 둔다 (정책을 하나도 추가하지 않으면 기본이 전체 차단).
alter table subscribers enable row level security;


-- ---------------------------------------------------------------------------
-- 아카이브 검색용 테이블.
--
-- 왜 만들었나: 검색이 원래 docs/search-index.json을 브라우저가 통째로 내려받는
-- 방식이었다. 하루 약 12KB씩 자라서 180일 상한에 도달하면 2.2MB가 되고, 그 상한
-- 때문에 180일 이전 기사는 아카이브에 남아 있는데도 검색으로는 못 찾았다.
-- 서버에서 검색하면 두 문제가 같이 사라진다(다운로드 0, 기간 제한 없음).
--
-- link를 기본키로 쓴다 — 파이프라인이 이미 링크로 중복을 판정하고 있어서
-- 자연 키로 맞고, 같은 날짜를 여러 번 동기화해도 자동으로 멱등해진다.
create table if not exists search_articles (
  link text primary key,
  date date not null,
  title text not null,
  source text not null,
  summary_ko text,
  summary_en text,
  -- 클라이언트 검색이 title+summary_ko+summary_en을 이어 붙여 부분 문자열로 찾던 것과
  -- 동작을 똑같이 맞추기 위한 생성 컬럼. 인덱스도 이 컬럼 하나에만 걸면 된다.
  search_text text generated always as (
    coalesce(title, '') || ' ' || coalesce(summary_ko, '') || ' ' || coalesce(summary_en, '')
  ) stored
);

-- 부분 문자열 검색('%질의%')은 앞에 와일드카드가 붙어 B-tree 인덱스를 못 쓴다.
-- pg_trgm의 GIN 인덱스는 이 형태를 지원해서, 기사가 수만 건이 돼도 전체 스캔을 피한다.
-- 한국어에 Postgres 전문검색(to_tsvector)을 쓰지 않은 이유: 기본 제공되는 한국어 사전이
-- 없어 형태소 분리가 안 되고, 조사가 붙는 한국어에서는 오히려 부분 문자열 검색이
-- 기대에 더 가깝게 동작한다(기존 클라이언트 검색도 부분 문자열이었다).
create extension if not exists pg_trgm;
create index if not exists search_articles_search_text_trgm
  on search_articles using gin (search_text gin_trgm_ops);
create index if not exists search_articles_date_idx on search_articles (date desc);

alter table search_articles enable row level security;

-- 검색은 PostgREST 필터 문법(*, 쉼표, 괄호 등)을 쓰지 않고 이 함수로만 호출한다.
-- 질의어를 URL 필터가 아니라 JSON 본문의 함수 인자로 넘기게 되어, 사용자 입력이
-- 필터 문법으로 해석될 여지가 원천적으로 없어진다.
-- LIKE 와일드카드(%, _)와 이스케이프 문자(\)는 함수 안에서 무력화해, 사용자가 무엇을
-- 입력하든 "그 글자 그대로 포함"만 찾는다.
create or replace function search_archive(q text, max_results int default 20)
returns table (date date, title text, link text, source text)
language sql
stable
as $$
  select a.date, a.title, a.link, a.source
  from search_articles a
  where a.search_text ilike
        '%' || replace(replace(replace(q, '\', '\\'), '%', '\%'), '_', '\_') || '%'
  order by a.date desc, a.title
  limit least(greatest(coalesce(max_results, 20), 1), 50);
$$;
