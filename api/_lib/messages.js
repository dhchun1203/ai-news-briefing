// 구독 관련 페이지·메일에 나가는 모든 문구를 한 곳에 모은다.
//
// 왜 문구를 코드에서 분리했나: /en/ 에서 구독한 독자에게 한국어 확인 메일과 한국어
// 결과 페이지가 나가고 있었다. 문구가 핸들러마다 하드코딩돼 있으면 언어 분기를 한 곳
// 빠뜨려도 아무도 모른다 — 그 화면을 한국어 사용자는 볼 일이 없기 때문이다.
// 여기 모아두면 "두 언어가 다 있는가"를 테스트가 기계적으로 확인할 수 있다.
//
// 새 문구를 추가할 때는 반드시 ko/en을 함께 넣는다. tests/api_handlers.test.js가
// 한쪽만 있는 키를 잡아낸다.

const LANGS = ["ko", "en"];

// 지원하지 않는 값이 오면 조용히 한국어로 떨어뜨린다. 언어는 화면 표시에만 쓰이므로
// 잘못된 값 때문에 요청을 실패시킬 이유가 없다.
function normalizeLang(value) {
  const lang = String(value || "").trim().toLowerCase();
  return LANGS.includes(lang) ? lang : "ko";
}

const MESSAGES = {
  // --- /api/confirm ---
  confirm_ok: {
    ko: {
      title: "구독 확인 완료",
      body: "내일 아침 8시부터 AI 뉴스 브리핑을 이메일로 받아보실 수 있어요.",
    },
    en: {
      title: "Subscription confirmed",
      body: "You'll get the AI news briefing by email from the next issue on. It goes out at 8AM KST — that's the evening before in the US.",
    },
  },
  confirm_bad_link: {
    ko: { title: "확인 실패", body: "잘못된 확인 링크입니다." },
    en: { title: "Confirmation failed", body: "That confirmation link is malformed." },
  },
  confirm_invalid: {
    ko: { title: "확인 실패", body: "유효하지 않은 확인 링크입니다." },
    en: { title: "Confirmation failed", body: "That confirmation link isn't valid." },
  },
  confirm_expired: {
    ko: {
      title: "확인 링크 만료",
      body: "확인 링크가 만료됐어요. 아래 버튼을 누르면 새 링크를 보내드립니다.",
      button: "확인 메일 다시 받기",
    },
    en: {
      title: "Link expired",
      body: "This confirmation link has expired. Press the button below and we'll send a new one.",
      button: "Send me a new link",
    },
  },
  confirm_resent: {
    ko: {
      title: "확인 메일 발송",
      body: "새 확인 링크를 보내드렸어요. 메일함을 확인해주세요 (7일 이내 유효).",
    },
    en: {
      title: "New link sent",
      body: "We've sent a new confirmation link. Check your inbox — it's valid for 7 days.",
    },
  },
  confirm_already: {
    ko: { title: "이미 확인됨", body: "이미 구독이 확정된 주소예요. 매일 아침 8시에 보내드립니다." },
    en: {
      title: "Already confirmed",
      body: "This address is already subscribed. The briefing goes out daily at 8AM KST.",
    },
  },
  confirm_no_record: {
    ko: { title: "확인 메일 발송", body: "구독 신청 기록이 없어요. 사이트에서 다시 신청해주세요." },
    en: {
      title: "No subscription found",
      body: "We have no signup on record for this address. Please subscribe again from the site.",
    },
  },

  // --- /api/unsubscribe ---
  unsub_confirm: {
    ko: {
      title: "구독취소 확인",
      body: "아래 주소의 구독을 취소하시겠어요?",
      button: "구독취소",
      note: "버튼을 누르기 전까지는 취소되지 않습니다.",
    },
    en: {
      title: "Confirm unsubscribe",
      body: "Unsubscribe this address?",
      button: "Unsubscribe",
      note: "Nothing changes until you press the button.",
    },
  },
  unsub_invalid: {
    ko: { title: "처리 실패", body: "유효하지 않은 구독취소 링크입니다." },
    en: { title: "Request failed", body: "That unsubscribe link isn't valid." },
  },
  unsub_ok: {
    ko: {
      title: "구독취소 완료",
      body: "더 이상 이메일이 발송되지 않습니다. 언제든 다시 구독하실 수 있어요.",
    },
    en: {
      title: "Unsubscribed",
      body: "You won't receive any more emails. You're welcome back any time.",
    },
  },

  // --- 공통 오류 ---
  method_not_allowed: {
    ko: { title: "처리 실패", body: "지원하지 않는 요청입니다." },
    en: { title: "Request failed", body: "That request method isn't supported." },
  },
  server_error: {
    ko: { title: "오류", body: "서버 설정 오류로 처리하지 못했습니다." },
    en: { title: "Error", body: "A server configuration problem prevented this from completing." },
  },
  db_error: {
    ko: { title: "오류", body: "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요." },
    en: { title: "Error", body: "Something went wrong. Please try again in a moment." },
  },
  send_error: {
    ko: { title: "오류", body: "메일 발송에 실패했어요. 잠시 후 다시 시도해주세요." },
    en: { title: "Error", body: "We couldn't send the email. Please try again in a moment." },
  },

  // --- 페이지 공통 ---
  back_link: { ko: { body: "브리핑으로 돌아가기" }, en: { body: "Back to the briefing" } },
};

function t(lang, key) {
  const entry = MESSAGES[key];
  if (!entry) throw new Error(`unknown message key: ${key}`);
  return entry[normalizeLang(lang)];
}

// 언어별 홈 경로. 영어 독자를 한국어 홈으로 보내면 되돌아올 방법이 없다.
// cleanUrls 때문에 /en/index.html은 /en으로 308 리다이렉트되므로 처음부터 /en을 쓴다.
function homePath(lang) {
  return normalizeLang(lang) === "en" ? "/en" : "/";
}

module.exports = { MESSAGES, LANGS, normalizeLang, t, homePath };
