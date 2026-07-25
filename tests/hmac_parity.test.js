// Python(scripts/send_broadcast.py)과 Node(api/_lib/tokens.js)가 같은 구독취소 토큰을
// 만들어내는지 확인한다.
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

console.log(`\n${pass}/${cases.length} passed`);
process.exit(pass === cases.length ? 0 : 1);
