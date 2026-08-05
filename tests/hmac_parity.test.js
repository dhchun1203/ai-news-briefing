// Python과 Node(api/_lib/tokens.js)가 같은 토큰을 만들어내는지 확인한다.
//
// 두 가지 계약이 걸려 있다:
//   - 구독취소 토큰: scripts/send_broadcast.py가 서명 -> Node가 검증
//   - 확인 토큰:     scripts/remind_unconfirmed.py가 서명 -> Node가 검증
//
// 왜 이게 중요한가: 구독취소 링크는 **파이썬이 서명해서** 매일 메일에 넣고, 그 링크를
// 검증하는 건 **Node 서버리스 함수**다. 두 구현이 어긋나면 모든 구독자의 구독취소
// 링크가 한꺼번에 죽는데, 정작 코드상으로는 아무 데도 연결돼 있지 않아 조용히 깨진다.
// (base64url 패딩 처리, 페이로드 구분자 등이 어긋나기 쉬운 지점이다.)
const path = require("path");
const { execFileSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const SECRET = "parity-test-secret-do-not-use-in-prod";
process.env.SUBSCRIBE_TOKEN_SECRET = SECRET;

const tokens = require(path.join(ROOT, "api/_lib/tokens.js"));

// 로컬(Windows)은 py, CI(Linux)는 python3 — 실제로 동작하는 쪽을 쓴다.
// Windows에는 실행하면 스토어로 보내며 exit 9009로 끝나는 python3.exe 스텁이 있어서
// ENOENT만 걸러내는 방식으로는 부족하다 — 출력이 나오는지까지 봐야 한다.
function python(args) {
  const errors = [];
  for (const exe of ["python3", "py", "python"]) {
    try {
      const out = execFileSync(exe, args, { cwd: ROOT, encoding: "utf-8", stdio: ["ignore", "pipe", "pipe"] });
      if (out && out.trim()) return out.trim();
      errors.push(`${exe}: empty output`);
    } catch (e) {
      errors.push(`${exe}: ${e.code || e.status}`);
    }
  }
  throw new Error("no working python interpreter found -> " + errors.join(", "));
}

const cases = [
  "user@example.com",
  "UPPER.Case+tag@sub.domain.co.kr",
  "a@b.io",
];

let pass = 0;
for (const email of cases) {
  const fromNode = tokens.makeUnsubscribeToken(email);
  const fromPython = python([
    "-c",
    [
      "import sys",
      "sys.path.insert(0, 'scripts')",
      "from send_broadcast import sign",
      `print(sign(${JSON.stringify(SECRET)}, 'unsubscribe|' + ${JSON.stringify(email)}))`,
    ].join("; "),
  ]);
  const ok = fromNode === fromPython;
  console.log((ok ? "PASS " : "FAIL ") + `unsubscribe token parity: ${email}`);
  if (!ok) console.log(`   node=${fromNode}\n   py  =${fromPython}`);
  if (ok) pass++;
}

// --- 확인 토큰: 리마인더 링크를 파이썬이 만들고 Node가 검증한다 ---
// 어긋나면 리마인더의 링크만 전부 죽는데, 사람이 눌러보기 전까지 아무도 모른다.
let total = cases.length;
const EXPIRY = 2000000000;
for (const email of cases) {
  const fromNode = require("crypto")
    .createHmac("sha256", SECRET)
    .update(`confirm|${email}|${EXPIRY}`)
    .digest("base64url");
  const fromPython = python([
    "-c",
    [
      "import sys",
      "sys.path.insert(0, 'scripts')",
      "from remind_unconfirmed import sign",
      `print(sign(${JSON.stringify(SECRET)}, 'confirm|' + ${JSON.stringify(email)} + '|${EXPIRY}'))`,
    ].join("; "),
  ]);
  const ok = fromNode === fromPython;
  console.log((ok ? "PASS " : "FAIL ") + `confirm token parity: ${email}`);
  if (ok) pass++;
  total++;
}

// 파이썬이 만든 링크를 Node가 실제로 통과시키는지 — 서명뿐 아니라 유효기간까지 맞아야 한다.
{
  const url = python([
    "-c",
    [
      "import sys",
      "sys.path.insert(0, 'scripts')",
      "from remind_unconfirmed import confirm_url",
      `print(confirm_url('https://x.test', ${JSON.stringify(SECRET)}, 'u@x.com'))`,
    ].join("; "),
  ]);
  const q = new URL(url).searchParams;
  const verdict = tokens.verifyConfirmToken(q.get("email"), q.get("expiry"), q.get("token"));
  console.log((verdict.ok ? "PASS " : "FAIL ") + "python confirm link verifies in Node");
  if (!verdict.ok) console.log("   reason=" + verdict.reason + " url=" + url);
  if (verdict.ok) pass++;
  total++;

  // TTL이 어긋나면 리마인더 링크만 예고 없이 일찍 만료된다.
  const ttl = Number(q.get("expiry")) - Math.floor(Date.now() / 1000);
  const same = Math.abs(ttl - tokens.CONFIRM_TTL_SECONDS) <= 5;
  console.log((same ? "PASS " : "FAIL ") + "confirm TTL matches between Python and Node");
  if (!same) console.log(`   py=${ttl}s node=${tokens.CONFIRM_TTL_SECONDS}s`);
  if (same) pass++;
  total++;
}

console.log(`\n${pass}/${total} passed`);
process.exit(pass === total ? 0 : 1);
