# 모델 오케스트레이션

이 프로젝트는 Claude Fable 5를 리더(coordinator)로 두는 계층형 오케스트레이션을 기본으로
한다. 리더는 계획·분해·판단·최종 검수를 맡고, 실제 대량 생성과 반복 작업은 하위 모델에
위임한다.

## 역할 배분

| 역할 | 모델 ID | 담당 |
|---|---|---|
| 리더 / coordinator | `claude-fable-5` | 문제 분해, 위임 계획, 교차 검증, 최종 판단 |
| 주력 실행자 | `claude-opus-5` | 복잡한 코딩, 다중 파일 리팩터, 장기 에이전트 작업 |
| 대량 실행자 | `claude-sonnet-5` | 일반 구현, 테스트 작성, 문서화, 반복 작업 |
| 경량 실행자 | `claude-haiku-4-5` | 분류, 추출, 포맷 변환, 라우팅 판단 |

모델 ID는 위 문자열 그대로 사용한다. 날짜 접미사(`-20260101` 등)를 붙이지 않는다.

## 위임 원칙

1. **리더는 만들지 않고 정한다.** Fable 5에서 대량 코드/문서를 직접 생성하지 않는다
   (입력 $10 / 출력 $50 per MTok — Opus 5의 2배). 리더의 출력은 계획, 위임 지시,
   검수 결과여야 한다.
2. **위임 깊이는 1단계.** 하위 실행자는 다시 위임하지 않는다. Managed Agents의
   coordinator 로스터도 1단계만 허용되며, 로스터에 든 에이전트가 자체 multiagent
   설정을 가지면 생성 자체가 검증 오류로 거부된다.
3. **작업 명세는 첫 턴에 전부 준다.** Fable 5·Opus 5 모두 초기 턴에 전체 명세가 주어진
   장기 자율 실행에서 가장 좋은 결과를 낸다. 여러 턴에 걸쳐 요구사항을 흘리면 토큰
   효율과 품질이 함께 떨어진다.
4. **위임 대상이 애매하면 한 단계 위 모델로 올린다.** 재시도 비용이 모델 등급 차이보다
   크다.
5. **검수는 별도 컨텍스트에서.** 자기 비평보다 새 컨텍스트의 검증자 하위 에이전트가 낫다.

## 실행자 선택 기준

Haiku 4.5로 시작해서 필요할 때만 올린다 — 단, 아래에 해당하면 처음부터 해당 등급으로 간다.

- 다중 파일 수정 / 아키텍처 변경 / 장기 에이전트 루프 → `claude-opus-5`
- 단일 파일 구현, 테스트, 문서, 정형 변환 → `claude-sonnet-5`
- 단일 판정, 라벨링, 추출, 200K 컨텍스트로 충분한 작업 → `claude-haiku-4-5`

**컨텍스트 한계**: Fable 5 / Opus 5 / Sonnet 5는 1M(입력) · 128K(출력), Haiku 4.5는
200K · 64K. Haiku에 1M급 입력을 넘기지 않는다.

## effort 설정

`output_config.effort`로 지정한다 (top-level 아님). 기본값은 `high`.

- **리더(Fable 5)**: `high` 기본, 가장 어려운 판단만 `xhigh`
- **Opus 5 코딩/에이전트**: `xhigh`로 시작한 뒤 `medium`까지 내려가며 스윕. Opus 5는
  low/medium에서도 강하다 — 이전 모델의 effort 기본값을 그대로 가져오지 말 것.
- **Sonnet 5**: `high` 유지, 가장 어려운 코딩만 `xhigh`
- **Haiku 4.5**: effort 미지원. 보내면 에러.

## 캐시 규율

프롬프트 캐시는 **모델 단위**다. 대화 도중 모델을 바꾸면 캐시가 전부 무효화된다.

- 메인 루프는 한 모델로 고정한다. 저렴한 모델이 필요하면 모델을 바꾸지 말고 하위
  에이전트를 띄운다.
- 도구 목록(`tools`)은 prefix 맨 앞에 렌더링된다. 대화 중 추가/삭제/재정렬 금지.
- 시스템 프롬프트에 타임스탬프·UUID·세션 ID를 넣지 않는다. 중간에 지시를 추가해야 하면
  `messages[]`에 `{"role": "system", ...}` 메시지를 덧붙인다 (Fable 5 / Opus 5 /
  Opus 4.8 지원, beta 헤더 불필요. Sonnet 5는 미지원).

## 모델별 API 제약 (위반 시 400)

### `claude-fable-5`

- `thinking` 파라미터를 **아예 생략**한다. thinking은 항상 켜져 있다.
  `{"type": "disabled"}`도 `{"type": "enabled", "budget_tokens": N}`도 400.
- raw chain of thought는 반환되지 않는다. 사용자에게 추론을 보여줘야 하면
  `thinking: {"type": "adaptive", "display": "summarized"}`로 요약본을 받는다
  (기본값은 `"omitted"` — 빈 문자열).
- assistant prefill 불가.
- `temperature` / `top_p` / `top_k` 불가.
- **30일 데이터 보존 필수.** ZDR 조직은 모든 요청이 400. 요청 본문을 디버깅하기 전에
  조직 보존 설정부터 확인할 것.

### `claude-opus-5`

- thinking이 **기본 ON**. thinking을 생략하면 adaptive로 동작한다 (Opus 4.8과 반대).
- `thinking: {"type": "disabled"}`는 effort `high` 이하에서만 허용. `xhigh`/`max`와 함께
  쓰면 400.
- **thinking을 끄지 말 것.** 끄면 도구 호출이 구조화된 `tool_use` 블록 대신 평문 텍스트로
  나올 수 있다 — 에러 없이 호출이 그냥 실행되지 않는다. 비용을 줄이려면 thinking을 켠 채
  effort를 low/medium으로 내린다.
- `budget_tokens` / 샘플링 파라미터 / prefill 불가.
- 프롬프트 캐시 최소 길이 **512 토큰** (Opus 4.8은 1024).

### `claude-sonnet-5`

- thinking 기본 ON (adaptive). `budget_tokens` 제거됨.
- 비기본값 샘플링 파라미터 400. prefill 400.
- **새 토크나이저** — 같은 텍스트가 Sonnet 4.6 대비 약 30% 더 많은 토큰.
  `max_tokens`와 비용 기준선을 다시 잡을 것.

### 공통

- `max_tokens`가 ~16000을 넘으면 **반드시 스트리밍**한다. 스트리밍 없이 큰 값을 쓰면
  SDK HTTP 타임아웃.
- `xhigh`/`max` effort에서는 `max_tokens`를 최소 64000으로 둔다. thinking + 응답이 같은
  예산을 나눠 쓰기 때문에 부족하면 답변이 잘린다.

## 거부(refusal) 처리 — 리더 필수

Fable 5와 Opus 5는 안전 분류기가 요청을 거부할 수 있다. **HTTP 200에
`stop_reason: "refusal"`로 오므로 에러로 잡히지 않는다.**

- `response.content[0]`을 무조건 읽지 말고 `stop_reason`을 먼저 분기한다. 거부 시
  `content`는 비어 있거나 부분 출력이다.
- `stop_details`가 아니라 `stop_reason`으로 분기한다 — 거부여도 `stop_details`가 null일
  수 있다.
- 서버사이드 폴백을 기본으로 켠다: beta `server-side-fallback-2026-07-01` +
  `fallbacks: "default"`. 거부 카테고리에 따라 Anthropic이 대체 모델로 라우팅하므로 모델
  목록을 직접 관리할 필요가 없다.
- 출력 전 거부는 과금되지 않고, 스트리밍 중 거부는 이미 흘러간 부분만 과금된다.

## Managed Agents로 구성할 때

리더-실행자 구조를 API 네이티브로 표현하려면 coordinator 로스터를 쓴다. `multiagent`는
agent 객체의 **top-level 필드**이며 `tools[]` 항목이 아니다.

```python
coordinator = client.beta.agents.create(
    name="Lead",
    model={"id": "claude-fable-5", "effort": "high"},
    system="당신은 작업을 분해하고 하위 에이전트에 위임한다. 직접 대량 생성하지 않는다.",
    tools=[{"type": "agent_toolset_20260401"}],
    multiagent={
        "type": "coordinator",
        "agents": [opus_worker.id, sonnet_worker.id, haiku_worker.id],
    },
)
```

- agent는 한 번만 생성하고 ID를 저장해 재사용한다. 요청 경로에서 `agents.create()`를
  호출하지 않는다.
- effort는 agent 설정에서만 유효하다. 세션의 model 오버라이드에 넣은 effort는 조용히
  무시된다.
- 로스터 최대 20개 에이전트, 동시 스레드 최대 25개.
- `agents.archive()`는 되돌릴 수 없다 — 새 세션이 그 에이전트를 참조할 수 없게 된다.
  정리 목적으로 호출하지 말 것.

## Claude Code 하위 에이전트로 구성할 때

Agent 툴의 `model` 파라미터, 또는 `.claude/agents/*.md` frontmatter의 `model:` 필드로
지정한다. 허용값은 `fable` / `opus` / `sonnet` / `haiku`.

- **리더 세션이 fable일 때만 이 문서의 위임 규칙이 적용된다.**
- 하위 에이전트는 매번 빈 컨텍스트에서 시작한다. 위임 프롬프트에 파일 경로와 배경을 전부
  담아 자립적으로 만든다.
- 병렬 위임은 독립적인 작업 갈래에만 쓴다. 파일 몇 개 읽고 끝나는 일은 직접 처리한다.
