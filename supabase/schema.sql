-- Supabase SQL Editor에서 한 번 실행한다.
-- 이메일 구독자 원본 데이터를 저장하는 테이블. 확인(더블 옵트인) 전/후, 구독 취소 여부를
-- 모두 여기 한 곳에 누적한다 (Resend는 발송만 담당, 구독자 목록의 진실 소스는 이 테이블).

create table if not exists subscribers (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  created_at timestamptz not null default now(),
  confirmed_at timestamptz,
  unsubscribed_at timestamptz
);

-- 서버리스 함수(Vercel)와 배포 파이프라인(scripts/send_broadcast.py)은 모두
-- service_role 키로 접근하므로 RLS 정책을 별도로 만들 필요는 없지만, anon/public 키로는
-- 아무 것도 접근하지 못하도록 RLS를 켜 둔다 (정책을 하나도 추가하지 않으면 기본이 전체 차단).
alter table subscribers enable row level security;
