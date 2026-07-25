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

-- 서버리스 함수(Vercel)와 배포 파이프라인(scripts/send_broadcast.py)은 모두
-- service_role 키로 접근하므로 RLS 정책을 별도로 만들 필요는 없지만, anon/public 키로는
-- 아무 것도 접근하지 못하도록 RLS를 켜 둔다 (정책을 하나도 추가하지 않으면 기본이 전체 차단).
alter table subscribers enable row level security;
