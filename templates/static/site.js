/* 모든 페이지(오늘자/아카이브/영어권 착지/주간 회고/용어사전)가 공유하는 클라이언트 스크립트.
 *
 * 예전에는 이 코드가 site.html.j2 / weekly.html.j2 / glossary.html.j2 세 템플릿에 통째로
 * 복붙돼 있었다(페이지마다 170~205줄이 인라인으로 재전송). 사본이 서로 어긋나면서 실제로
 * 버그가 생겼다 — weekly에는 언어 전환 시 updatePlaceholders() 호출이 빠져 있었고,
 * 용어 패널을 닫는 방식이 페이지마다 달랐으며, 같은 데이터에 id가 두 개(glossary-data /
 * glossary-lookup-data) 붙어 있었다. 그래서 하나로 합쳤다.
 *
 * 페이지마다 존재하는 요소가 다르지만 모든 블록이 `if (요소)` 가드로 시작하므로, 없는
 * 기능은 자연히 아무 일도 하지 않는다.
 *
 * 페이지별 설정은 <html>의 data-* 속성으로 받는다(템플릿이 Jinja로 채운다):
 *   data-default-lang   ko | en   — /en/ 착지 페이지는 en
 *   data-asset-prefix   ""  | "../"  — search-index.json 등 루트 자산 상대 경로
 *   data-archive-prefix 검색 결과에서 아카이브 페이지로 링크할 때 쓰는 접두사
 *
 * FOUC 방지 스크립트는 이 파일에 넣지 않는다 — 첫 페인트 전에 실행돼야 해서 각 템플릿
 * <head>에 인라인으로 남아 있다.
 */
(function () {
  "use strict";

  var root = document.documentElement;
  var config = {
    defaultLang: root.getAttribute("data-default-lang") || "ko",
    assetPrefix: root.getAttribute("data-asset-prefix") || "",
    archivePrefix: root.getAttribute("data-archive-prefix") || ""
  };

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : null;
  }

  function currentLang() {
    return root.getAttribute("data-lang") || "ko";
  }

  /* ---------- 배경 스크롤 잠금 ----------
   * 반투명 백드롭이 덮인 상태(용어 패널·모바일 서랍)는 모달이다. 그런데 뒤의 본문이
   * 계속 스크롤돼서, 패널을 열어둔 채 휠이나 방향키를 쓰면 읽던 자리를 잃는다.
   * 닫고 나면 엉뚱한 곳에 와 있다.
   *
   * 둘이 동시에 열릴 수 있으므로 카운터로 센다 — 하나가 닫힐 때 무조건 풀어버리면
   * 다른 하나가 아직 열려 있는데도 배경이 다시 움직인다.
   *
   * 스크롤바가 사라지면서 본문이 그 폭만큼 옆으로 튀는 것은 같은 폭의 padding으로 막는다
   * (스크롤바를 겹쳐 그리는 환경에서는 폭이 0이라 아무것도 하지 않는다). */
  var scrollLocks = 0;
  var lockedScrollY = 0;
  function lockBackgroundScroll() {
    if (++scrollLocks > 1) return;
    // 위치를 직접 기억했다가 되돌린다. overflow:hidden을 걸면 문서가 스크롤 불가능해져
    // 브라우저가 위치를 0으로 정리해버리는 환경이 있다(모바일 폭에서 실측: 잠금 중에는
    // pageYOffset이 1200으로 보이지만 풀면 0으로 떨어졌다).
    lockedScrollY = window.pageYOffset || root.scrollTop || 0;
    var barWidth = window.innerWidth - root.clientWidth;
    root.style.overflow = "hidden";
    if (barWidth > 0) root.style.paddingRight = barWidth + "px";
  }
  function unlockBackgroundScroll() {
    if (scrollLocks === 0 || --scrollLocks > 0) return;
    root.style.overflow = "";
    root.style.paddingRight = "";
    // behavior를 명시해야 CSS의 scroll-behavior: smooth를 덮는다 — 안 그러면 복원이
    // 애니메이션으로 보여서 화면이 출렁인다.
    window.scrollTo({ top: lockedScrollY, left: 0, behavior: "auto" });
  }

  /* ---------- 언어에 따라 화면에 안 보이는 문구도 교체 ----------
   * 본문은 .lang-ko/.lang-en을 CSS로 숨기고 보여주는 방식이라 알아서 바뀌지만,
   * placeholder와 aria-label은 속성값이라 그 방식이 통하지 않는다. 그대로 두면
   * 영어 모드로 보고 있는 스크린리더 사용자가 "다크모드 전환" 같은 한국어 라벨을
   * 그대로 듣게 된다. */
  function updateLocalizedAttrs() {
    var lang = currentLang();
    var suffix = lang === "en" ? "-en" : "-ko";
    Array.prototype.forEach.call(document.querySelectorAll("[data-placeholder-ko]"), function (el) {
      el.setAttribute("placeholder", el.getAttribute("data-placeholder" + suffix) || "");
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-aria-ko]"), function (el) {
      el.setAttribute("aria-label", el.getAttribute("data-aria" + suffix) || "");
    });
  }
  updateLocalizedAttrs();

  /* ---------- 다크모드 토글 ---------- */
  var themeBtn = document.getElementById("theme-toggle");
  if (themeBtn) {
    // 시스템 다크모드 설정과 무관하게, 쿠키에 저장된 명시적 선택이 없으면 항상 라이트가 기본값.
    var isDarkActive = function () {
      return root.getAttribute("data-theme") === "dark";
    };
    var setThemeCookie = function (value) {
      var expires = new Date();
      expires.setTime(expires.getTime() + 365 * 24 * 60 * 60 * 1000);
      document.cookie =
        "theme=" + encodeURIComponent(value) + "; expires=" + expires.toUTCString() + "; path=/; SameSite=Lax";
    };
    themeBtn.setAttribute("aria-checked", String(isDarkActive()));
    themeBtn.addEventListener("click", function () {
      var next = isDarkActive() ? "light" : "dark";
      root.setAttribute("data-theme", next);
      setThemeCookie(next);
      themeBtn.setAttribute("aria-checked", String(next === "dark"));
    });
  }

  /* ---------- bfcache 복원 시 테마 재동기화 ----------
   * 뒤로가기/앞으로가기로 브라우저가 페이지를 bfcache에서 복원하면(pageshow의
   * persisted===true) 스크립트가 다시 실행되지 않아 테마가 "떠날 때의 상태"로 얼어붙는다.
   * 언어는 URL이 결정하므로 여기서 되돌릴 것이 없다. */
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    var t = getCookie("theme");
    if (t === "dark" || t === "light") {
      root.setAttribute("data-theme", t);
      if (themeBtn) themeBtn.setAttribute("aria-checked", String(t === "dark"));
    }
  });

  /* ---------- 모바일 내비 서랍 (햄버거) ----------
     유틸리티 바에 내비 링크 2개 + 공유 + 언어 + 다크모드를 모두 넣으면 최소 412px가
     필요해 대부분의 폰(SE 320 / 13 mini 360 / 14 390)에서 두 줄로 감겼다. 모바일에서는
     링크를 서랍으로 옮기고 햄버거만 남긴다.

     서랍 내용은 유틸리티 바에 이미 있는 링크를 복제해 만든다. 템플릿 4곳(site·glossary·
     weekly·topic)에 같은 마크업을 또 넣지 않으려는 것이고, 덕분에 각 페이지가 자기
     상대경로를 그대로 들고 온다(경로를 다시 계산하지 않으므로 /topics 404 같은 사고가
     재발할 여지가 없다). 이 블록이 통째로 실패해도 링크는 바에 남아 있어 기존 동작이 된다. */
  var utilityBar = document.querySelector(".utility-bar");
  var barNavLinks = utilityBar ? utilityBar.querySelectorAll(".site-nav-link") : [];
  if (utilityBar && barNavLinks.length) {
    var drawer = document.createElement("aside");
    drawer.className = "nav-drawer";
    drawer.id = "nav-drawer";
    drawer.setAttribute("aria-hidden", "true");
    drawer.setAttribute("inert", "");

    var drawerClose = document.createElement("button");
    drawerClose.type = "button";
    drawerClose.className = "nav-drawer-close";
    drawerClose.innerHTML = "&times;";
    drawerClose.setAttribute("aria-label", currentLang() === "en" ? "Close menu" : "메뉴 닫기");
    drawer.appendChild(drawerClose);

    var drawerTitle = document.createElement("p");
    drawerTitle.className = "nav-drawer-title";
    drawerTitle.textContent = currentLang() === "en" ? "Menu" : "메뉴";
    drawer.appendChild(drawerTitle);

    // 홈·RSS는 페이지마다 경로가 달라서, 이미 문서에 있는 요소에서 주소를 그대로 빌린다.
    var homeAnchor = document.querySelector(".site-header h1 a");
    var feedLink = document.querySelector('link[type="application/rss+xml"]');
    var addDrawerLink = function (href, ko, en) {
      if (!href) return;
      var a = document.createElement("a");
      a.className = "site-nav-link";
      a.href = href;
      a.textContent = currentLang() === "en" ? en : ko;
      drawer.appendChild(a);
    };
    if (homeAnchor) addDrawerLink(homeAnchor.getAttribute("href"), "오늘자 브리핑", "Today's briefing");
    Array.prototype.forEach.call(barNavLinks, function (link) {
      var clone = link.cloneNode(true);
      clone.removeAttribute("id");  // 복제로 id가 중복되면 문서가 깨진다
      drawer.appendChild(clone);
    });
    if (feedLink) addDrawerLink(feedLink.getAttribute("href"), "RSS 구독", "RSS feed");

    var drawerBackdrop = document.createElement("div");
    drawerBackdrop.className = "nav-drawer-backdrop";
    drawerBackdrop.hidden = true;

    var navToggle = document.createElement("button");
    navToggle.type = "button";
    navToggle.className = "nav-toggle";
    navToggle.id = "nav-toggle";
    navToggle.setAttribute("aria-expanded", "false");
    navToggle.setAttribute("aria-controls", "nav-drawer");
    navToggle.setAttribute("aria-label", currentLang() === "en" ? "Open menu" : "메뉴 열기");
    navToggle.innerHTML =
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
      '<line x1="3" y1="6" x2="21" y2="6"></line>' +
      '<line x1="3" y1="12" x2="21" y2="12"></line>' +
      '<line x1="3" y1="18" x2="21" y2="18"></line></svg>';

    // 내용이 본문 칼럼 폭에 맞춰 가둬져 있으므로 바깥 .utility-bar가 아니라 안쪽
    // 컨테이너에 넣어야 다른 컨트롤과 같은 줄·같은 여백에 선다.
    var barInner = utilityBar.querySelector(".utility-bar-inner") || utilityBar;
    barInner.insertBefore(navToggle, barInner.firstChild);
    document.body.appendChild(drawerBackdrop);
    document.body.appendChild(drawer);
    // 이 요소들은 최초 updateLocalizedAttrs() 호출보다 늦게 만들어지므로, 영어 모드로
    // 들어온 방문자에게 aria-label이 한국어로 남지 않도록 여기서 한 번 더 맞춘다.
    updateLocalizedAttrs();

    var openDrawer = function () {
      drawer.classList.add("open");
      drawer.setAttribute("aria-hidden", "false");
      drawer.removeAttribute("inert");
      drawerBackdrop.hidden = false;
      lockBackgroundScroll();
      navToggle.setAttribute("aria-expanded", "true");
      drawerClose.focus();
    };
    var closeDrawer = function (returnFocus) {
      if (!drawer.classList.contains("open")) return;
      drawer.classList.remove("open");
      drawer.setAttribute("aria-hidden", "true");
      // 닫힌 서랍은 화면 밖으로 밀려나 있을 뿐 여전히 포커스를 받을 수 있다.
      // inert가 없으면 보이지 않는 링크에 탭 포커스가 갇힌다(용어 패널과 같은 이유).
      drawer.setAttribute("inert", "");
      drawerBackdrop.hidden = true;
      unlockBackgroundScroll();
      navToggle.setAttribute("aria-expanded", "false");
      // preventScroll이 없으면 화면 밖에 있는 햄버거로 포커스가 가면서 맨 위로 튄다.
      if (returnFocus) navToggle.focus({ preventScroll: true });
    };

    navToggle.addEventListener("click", openDrawer);
    drawerClose.addEventListener("click", function () { closeDrawer(true); });
    drawerBackdrop.addEventListener("click", function () { closeDrawer(true); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawer(true);
      // 열려 있는 동안 Tab이 서랍 밖으로 새지 않게 가둔다.
      if (e.key === "Tab" && drawer.classList.contains("open")) {
        var focusables = drawer.querySelectorAll("a[href], button");
        if (!focusables.length) return;
        var first = focusables[0];
        var last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    });
    // 링크를 눌러 페이지를 떠날 때 열린 상태가 bfcache에 남아 되돌아왔을 때
    // 서랍이 열린 채로 보이는 걸 막는다.
    window.addEventListener("pagehide", function () { closeDrawer(false); });
  }

  /* ---------- 이메일 구독 폼 ---------- */
  var subscribeForm = document.getElementById("subscribe-form");
  var subscribeStatus = document.getElementById("subscribe-status");
  if (subscribeForm && subscribeStatus) {
    var messages = {
      sending: { ko: "전송 중...", en: "Sending..." },
      confirm: {
        ko: "확인 메일을 보냈어요. 받은편지함에서 링크를 눌러 구독을 완료해주세요.",
        en: "Check your inbox — click the confirmation link to finish subscribing."
      },
      error: { ko: "문제가 발생했어요. 잠시 후 다시 시도해주세요.", en: "Something went wrong. Please try again." },
      network: { ko: "네트워크 오류가 발생했어요. 다시 시도해주세요.", en: "Network error. Please try again." }
    };
    messages.invalid = {
      ko: "이메일 주소 형식을 확인해주세요.",
      en: "Please check the email address format."
    };
    var setStatus = function (key) {
      subscribeStatus.textContent = messages[key][currentLang()];
    };

    /* ---- 오타 도메인 제안 ----
       실제로 ...@gmail.om 으로 구독을 시도한 사람이 확인 메일을 영영 못 받고
       유실됐다. 흔한 오타는 눈에 잘 안 띄고, 확인 메일이 안 오는 이유도 알 수 없다.

       **제안만 하고 막지는 않는다.** .om은 오만의 실존 국가 TLD이고 .co도 마찬가지라,
       하드 차단하면 정상 주소를 거절하게 된다. 사람이 보고 판단할 기회만 준다.

       MX 조회 같은 외부 호출은 하지 않는다 — 정적 사이트 구조를 유지하고, 무인
       운영 원칙상 외부 의존을 늘리지 않는다. 아래 표는 그래서 순수 문자열 비교다. */
    var COMMON_DOMAINS = [
      "gmail.com", "naver.com", "daum.net", "hanmail.net", "kakao.com",
      "outlook.com", "hotmail.com", "yahoo.com"
    ];
    // 로컬 파트(@ 앞)가 아니라 도메인만 본다.
    var TYPO_MAP = {
      // TLD 오타 — 맨 끝 글자가 빠지거나 뒤바뀌는 경우
      "gmail.om": "gmail.com", "gmail.con": "gmail.com", "gmail.cmo": "gmail.com",
      "gmail.co": "gmail.com", "gmail.comm": "gmail.com", "gmail.cm": "gmail.com",
      "naver.om": "naver.com", "naver.con": "naver.com", "naver.cmo": "naver.com",
      "daum.ne": "daum.net", "daum.nt": "daum.net", "daum.com": "daum.net",
      "hanmail.ne": "hanmail.net", "hanmail.nt": "hanmail.net",
      "kakao.om": "kakao.com", "kakao.con": "kakao.com",
      "outlook.om": "outlook.com", "outlook.con": "outlook.com",
      "hotmail.om": "hotmail.com", "hotmail.con": "hotmail.com",
      "yahoo.om": "yahoo.com", "yahoo.con": "yahoo.com",
      // 도메인 이름 자체의 오타
      "gmial.com": "gmail.com", "gamil.com": "gmail.com", "gmaill.com": "gmail.com",
      "gmai.com": "gmail.com", "gnail.com": "gmail.com",
      "navr.com": "naver.com", "nave.com": "naver.com", "naber.com": "naver.com",
      "hanmial.net": "hanmail.net", "hotmial.com": "hotmail.com",
      "outlok.com": "outlook.com", "yaho.com": "yahoo.com"
    };
    var suggestDomain = function (email) {
      var at = email.lastIndexOf("@");
      if (at < 0) return null;
      var domain = email.slice(at + 1).toLowerCase();
      if (!domain || COMMON_DOMAINS.indexOf(domain) >= 0) return null;
      return TYPO_MAP[domain] || null;
    };

    var hint = document.getElementById("subscribe-hint");
    var clearHint = function () {
      if (hint) { hint.textContent = ""; hint.hidden = true; }
    };
    var showSuggestion = function (email, fixedDomain, input) {
      if (!hint) return;
      var fixed = email.slice(0, email.lastIndexOf("@") + 1) + fixedDomain;
      var ko = currentLang() === "ko";
      hint.hidden = false;
      hint.textContent = ko ? "혹시 " : "Did you mean ";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "subscribe-hint-fix";
      btn.textContent = fixed;
      btn.addEventListener("click", function () {
        input.value = fixed;
        clearHint();
        input.focus();
      });
      hint.appendChild(btn);
      hint.appendChild(document.createTextNode(ko ? " 아닌가요?" : "?"));
    };

    var browserTimezone = function () {
      try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
      } catch (e) {
        return null;
      }
    };

    var emailInput = subscribeForm.querySelector('input[name="email"]');
    if (emailInput) {
      // 입력 중에는 방해하지 않고, 필드를 벗어날 때 한 번만 본다.
      emailInput.addEventListener("blur", function () {
        var v = emailInput.value.trim();
        clearHint();
        var fix = suggestDomain(v);
        if (fix) showSuggestion(v, fix, emailInput);
      });
      emailInput.addEventListener("input", clearHint);
    }

    subscribeForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var input = subscribeForm.querySelector('input[name="email"]');
      var submitBtn = subscribeForm.querySelector(".subscribe-submit");
      var email = input.value.trim();

      // ① 형식 검사. type="email"이 브라우저 단에서 거르지만, 폼을 JS로 가로채므로
      //    여기서도 한 번 본다(구형 브라우저·자동완성 우회 대비). 최소한만 본다 —
      //    이메일 형식을 정규식으로 완전히 검증하려는 시도는 늘 정상 주소를 거절한다.
      if (!/^[^\s@]+@[^\s@.]+(\.[^\s@.]+)+$/.test(email)) {
        setStatus("invalid");
        input.focus();
        return;
      }
      // ② 오타 도메인이면 제안만 띄우고 전송은 그대로 진행한다.
      var fix = suggestDomain(email);
      if (fix) showSuggestion(email, fix, input);

      submitBtn.disabled = true;
      setStatus("sending");
      fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // 시간대는 기록 전용이다(발송 시각은 아직 08:00 KST 고정). 브라우저가 직접
        // 알려주는 IANA 이름이라 IP 조회가 필요 없다. 구형 브라우저나 차단 환경에서
        // 실패하면 그냥 빼고 보낸다 — 이 값 때문에 구독이 막히면 안 된다.
        //
        // lang은 다르다 — 이 값이 앞으로 그 사람이 받을 모든 메일의 언어를 정한다.
        // 이걸 안 보내던 동안 /en/ 에서 구독한 독자가 한국어 확인 메일과 한국어
        // 브리핑을 받고 있었다.
        body: JSON.stringify({ email: email, timezone: browserTimezone(), lang: currentLang() })
      })
        .then(function (r) {
          return r.json().then(function (data) {
            return { ok: r.ok, data: data };
          });
        })
        .then(function (result) {
          submitBtn.disabled = false;
          if (result.ok) {
            setStatus("confirm");
            subscribeForm.reset();
            clearHint();
          } else {
            setStatus("error");
          }
        })
        .catch(function () {
          submitBtn.disabled = false;
          setStatus("network");
        });
    });
  }

  /* ---------- 링크 복사 버튼 ---------- */
  var shareBtn = document.getElementById("share-button");
  var shareTooltip = document.getElementById("share-tooltip");
  var shareTooltipTimer = null;
  if (shareBtn) {
    shareBtn.addEventListener("click", function () {
      if (!navigator.clipboard || !navigator.clipboard.writeText) return;
      navigator.clipboard
        .writeText(window.location.href)
        .then(function () {
          if (!shareTooltip) return;
          // 텍스트를 여기서 넣어야 aria-live가 실제로 읽어준다 — 미리 DOM에 있고
          // 클래스만 토글하면 live region은 아무 변화도 감지하지 못한다.
          shareTooltip.textContent = currentLang() === "en" ? "Copied!" : "복사되었습니다";
          shareTooltip.classList.add("visible");
          if (shareTooltipTimer) clearTimeout(shareTooltipTimer);
          shareTooltipTimer = setTimeout(function () {
            shareTooltip.classList.remove("visible");
            shareTooltip.textContent = "";
          }, 1600);
        })
        .catch(function () {});
    });
  }

  /* ---------- 용어 설명 패널 ---------- */
  var termPanel = document.getElementById("term-panel");
  var termBackdrop = document.getElementById("term-panel-backdrop");
  var termClose = document.getElementById("term-panel-close");
  var termTitle = document.getElementById("term-panel-title");
  var termBody = document.getElementById("term-panel-body");
  var glossaryDataEl = document.getElementById("glossary-data");
  var glossaryData = {};
  if (glossaryDataEl) {
    try {
      glossaryData = JSON.parse(glossaryDataEl.textContent || "{}");
    } catch (e) {
      glossaryData = {};
    }
  }

  // 용어 그래프(용어사전 페이지)에서도 호출하므로 바깥 스코프에 둔다.
  var openTermPanel = function () {};

  if (termPanel && termBackdrop && termTitle && termBody) {
    var termTrigger = null;
    openTermPanel = function (term, entry, trigger) {
      var lang = currentLang();
      termTitle.textContent = term;
      termBody.textContent = entry[lang] || entry.ko || entry.en || "";
      termPanel.classList.add("open");
      termPanel.setAttribute("aria-hidden", "false");
      termPanel.removeAttribute("inert");
      // 이미 열려 있는데 다른 용어를 누른 경우 잠금을 두 번 걸지 않는다.
      var wasOpen = termBackdrop.hidden === false;
      termBackdrop.hidden = false;
      if (!wasOpen) lockBackgroundScroll();
      termTrigger = trigger || null;
      if (termClose) termClose.focus();
    };
    var closeTermPanel = function () {
      if (!termPanel.classList.contains("open")) return;
      termPanel.classList.remove("open");
      termPanel.setAttribute("aria-hidden", "true");
      // 닫힌 패널은 화면에서 밀려나 있을 뿐 여전히 포커스를 받을 수 있다. inert를 걸어
      // 탭 순서에서 완전히 빼지 않으면, 보이지도 않는 닫기 버튼에 포커스가 갇힌다
      // (게다가 aria-hidden 안에 포커스 가능한 요소가 있는 건 ARIA 위반이다).
      termPanel.setAttribute("inert", "");
      termBackdrop.hidden = true;
      unlockBackgroundScroll();
      if (termTrigger) {
        termTrigger.focus({ preventScroll: true });
        termTrigger = null;
      }
    };
    // 시작 상태는 닫힘 — inert를 걸어둔다.
    termPanel.setAttribute("inert", "");

    document.addEventListener("click", function (e) {
      var btn = e.target.closest && e.target.closest(".term-link");
      if (btn) {
        var term = btn.getAttribute("data-term");
        var entry = glossaryData[term];
        if (entry) openTermPanel(term, entry, btn);
        return;
      }
      if (e.target === termBackdrop) closeTermPanel();
    });
    if (termClose) termClose.addEventListener("click", closeTermPanel);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeTermPanel();
      // 패널이 열려있을 때 Tab이 밖으로 나가지 않게 가둔다 — 포커스 가능한 요소가
      // 닫기 버튼 하나뿐이라 항상 그 버튼으로 되돌린다(단순한 형태의 focus trap).
      if (e.key === "Tab" && termPanel.classList.contains("open")) {
        e.preventDefault();
        if (termClose) termClose.focus();
      }
    });
  }

  /* ---------- 용어사전: 이전 화면으로 돌아가기 ---------- */
  var glossaryBack = document.getElementById("glossary-back");
  if (glossaryBack) {
    // 용어사전은 오늘자/지난 아카이브/영어권 페이지 등 어디서든 들어올 수 있어
    // 고정된 링크 하나로는 정확한 원래 위치를 알 수 없다 — 실제 방문 이력으로 되돌아간다.
    // 직접 주소로 들어와 이력이 없는 경우(history.length가 1)에는 홈으로 대체.
    glossaryBack.addEventListener("click", function () {
      if (window.history.length > 1) window.history.back();
      else window.location.href = "index.html";
    });
  }

  /* ---------- 읽는 위치 표시 (데스크톱 좌측 레일 + 모바일 진행 바) ----------
   * GeekNews 피드백 2차: 기사 10건을 스크롤하는 동안 "지금 어디쯤인지" 알 수 없다.
   *
   * 하나의 관찰자가 두 표시를 함께 갱신한다 — 데스크톱은 좌측 레일에서 현재 항목을
   * 강조하고, 좁은 화면은 상단 한 줄짜리 진행 바에 "3/10 · 제목"을 띄운다.
   * 어느 쪽을 보여줄지는 CSS가 정한다(JS가 폭을 재서 분기하면 창 크기를 바꿀 때마다
   * 어긋난다).
   *
   * 링크는 기존 목차(.toc-list)를 복제해 만든다. 페이지마다 다른 상대경로를 다시
   * 계산하지 않으려는 것이고, 이 블록이 통째로 실패해도 본문과 목차는 그대로 남는다. */
  var articleList = document.querySelector(".article-list");
  var articleCards = articleList ? articleList.querySelectorAll(".article-card") : [];
  var tocList = document.querySelector(".toc-list");
  if (articleList && articleCards.length && tocList) {
    var isEnglish = currentLang() === "en";

    /* --- 좌측 레일 --- */
    var rail = document.createElement("nav");
    rail.className = "toc-rail";
    rail.id = "toc-rail";
    rail.setAttribute("aria-label", isEnglish ? "Article navigation" : "기사 목차");
    var railTitle = document.createElement("p");
    railTitle.className = "toc-rail-title";
    railTitle.textContent = isEnglish ? "Contents" : "목차";
    rail.appendChild(railTitle);

    var railOl = document.createElement("ol");
    var railItems = [];
    Array.prototype.forEach.call(tocList.querySelectorAll("li a"), function (a, i) {
      var li = document.createElement("li");
      var link = document.createElement("a");
      link.href = a.getAttribute("href");
      var num = document.createElement("span");
      num.className = "rail-num";
      num.textContent = ("0" + (i + 1)).slice(-2);
      var text = document.createElement("span");
      text.className = "rail-text";
      var src = a.querySelector(".toc-text");
      text.textContent = src ? src.textContent.trim() : a.textContent.trim();
      // 잘린 제목은 마우스를 올리면 전체가 보이게 한다.
      link.title = text.textContent;
      link.appendChild(num);
      link.appendChild(text);
      li.appendChild(link);
      railOl.appendChild(li);
      railItems.push(li);
    });
    rail.appendChild(railOl);
    document.body.appendChild(rail);

    /* --- 모바일 진행 바 --- */
    var progress = document.createElement("div");
    progress.className = "reading-progress";
    progress.id = "reading-progress";
    // 스크롤에 따라 계속 바뀌는 값이라 aria-live를 붙이면 스크린리더가 쉬지 않고 읽는다.
    progress.setAttribute("aria-hidden", "true");
    var progressCount = document.createElement("span");
    progressCount.className = "reading-progress-count";
    var progressSep = document.createElement("span");
    progressSep.className = "reading-progress-sep";
    progressSep.setAttribute("aria-hidden", "true");
    progressSep.textContent = "·";
    var progressTitle = document.createElement("span");
    progressTitle.className = "reading-progress-title";
    progress.appendChild(progressCount);
    progress.appendChild(progressSep);
    progress.appendChild(progressTitle);
    document.body.appendChild(progress);

    /* --- 현재 기사 판정 --- */
    var activeIndex = -1;
    var setActive = function (index) {
      if (index === activeIndex || index < 0 || index >= articleCards.length) return;
      activeIndex = index;
      railItems.forEach(function (li, i) {
        li.classList.toggle("active", i === index);
      });
      progressCount.textContent = index + 1 + "/" + articleCards.length;
      var titleEl = articleCards[index].querySelector(".article-title");
      progressTitle.textContent = titleEl ? titleEl.textContent.trim() : "";
    };

    // 화면 위쪽 1/3 지점을 "읽는 선"으로 삼는다. 그 선을 지나는 기사가 현재 기사다.
    // 기사를 펼쳐 높이가 늘어나도 이 방식은 그대로 맞는다 — 관찰자가 요소를 보지
    // 높이를 기억하지 않기 때문이다.
    if ("IntersectionObserver" in window) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (e) {
            if (!e.isIntersecting) return;
            var i = Array.prototype.indexOf.call(articleCards, e.target);
            if (i >= 0) setActive(i);
          });
        },
        { rootMargin: "-30% 0px -60% 0px", threshold: 0 }
      );
      Array.prototype.forEach.call(articleCards, function (c) {
        observer.observe(c);
      });
    }

    // 접힌 기사를 펼치면 아래 기사들이 밀려난다. 관찰자는 교차가 생길 때만 깨어나므로,
    // 펼침 직후 현재 위치를 한 번 다시 계산해준다.
    Array.prototype.forEach.call(document.querySelectorAll("details.article-more"), function (d) {
      d.addEventListener("toggle", function () {
        window.requestAnimationFrame(syncReadingState);
      });
    });

    /* --- 진행 바 표시 여부 --- */
    // 기사 목록을 읽는 동안에만 띄운다. 인사이트·FAQ 구간에서는 알려줄 위치가 없다.
    var progressTicking = false;
    function syncReadingState() {
      progressTicking = false;
      var line = 8;   // 진행 바가 top: 0에 붙으므로 그 바로 아래가 기준선이다
      var rect = articleList.getBoundingClientRect();
      var inside = rect.top <= line && rect.bottom > line;
      progress.classList.toggle("visible", inside);

      // 관찰자가 놓친 경우(아주 긴 기사가 읽는 선을 통째로 덮는 등)를 대비해
      // 스크롤할 때마다 현재 기사를 직접 계산한다.
      if (!inside) return;
      var readLine = window.innerHeight * 0.3;
      var current = -1;
      for (var i = 0; i < articleCards.length; i++) {
        if (articleCards[i].getBoundingClientRect().top <= readLine) current = i;
      }
      if (current >= 0) setActive(current);
    }
    window.addEventListener(
      "scroll",
      function () {
        if (progressTicking) return;
        progressTicking = true;
        window.requestAnimationFrame(syncReadingState);
      },
      { passive: true }
    );
    window.addEventListener("resize", function () {
      window.requestAnimationFrame(syncReadingState);
    });
    syncReadingState();
  }

  /* ---------- 맨 위로 ----------
   * 아카이브·용어사전 페이지는 스크롤이 길어서 상단 내비로 돌아가는 비용이 크다.
   * 햄버거와 같은 이유로 여기서 만들어 붙인다 — 템플릿 7곳에 같은 마크업을 넣지
   * 않으려는 것이고, 이 블록이 통째로 실패해도 페이지는 그대로 동작한다. */
  var scrollTopBtn = document.createElement("button");
  scrollTopBtn.type = "button";
  scrollTopBtn.className = "scroll-top";
  scrollTopBtn.id = "scroll-top";
  // 화면에 글자가 없는 아이콘 버튼이라 라벨이 없으면 스크린리더가 "버튼"이라고만 읽는다.
  scrollTopBtn.setAttribute("data-aria-ko", "맨 위로");
  scrollTopBtn.setAttribute("data-aria-en", "Back to top");
  scrollTopBtn.setAttribute("aria-label", currentLang() === "en" ? "Back to top" : "맨 위로");
  scrollTopBtn.innerHTML =
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<line x1="12" y1="19" x2="12" y2="5"></line>' +
    '<polyline points="5 12 12 5 19 12"></polyline></svg>';
  document.body.appendChild(scrollTopBtn);

  // 한 화면 반쯤 내려갔을 때부터 띄운다. 너무 일찍 뜨면 첫 화면부터 방해가 된다.
  var SCROLL_TOP_THRESHOLD = 600;
  var scrollTicking = false;
  var syncScrollTop = function () {
    var y = window.pageYOffset || root.scrollTop || 0;
    scrollTopBtn.classList.toggle("visible", y > SCROLL_TOP_THRESHOLD);
    scrollTicking = false;
  };
  // 스크롤 이벤트는 초당 수십 번 온다. rAF로 프레임당 한 번으로 묶는다.
  window.addEventListener("scroll", function () {
    if (scrollTicking) return;
    scrollTicking = true;
    window.requestAnimationFrame(syncScrollTop);
  }, { passive: true });
  syncScrollTop();

  scrollTopBtn.addEventListener("click", function () {
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    // 화면만 올라가고 포커스는 페이지 아래에 남으면, 키보드 사용자는 다음 탭에서
    // 다시 아래로 끌려간다. 포커스도 맨 위로 옮긴다.
    var heading = document.querySelector(".site-header h1");
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }
  });

  /* ---------- 다른 언어판 안내 ----------
   * 영어권 방문자가 dailyaithread.com으로 들어오면 전부 한국어인 페이지를 보고,
   * EN 스위치를 직접 찾아야 했다. 방문자 국가 1위가 미국이라 조용한 손실이었다.
   *
   * **리다이렉트하지 않는다.** 감지된 언어로 자동 이동시키면 크롤러와 사람이 한쪽
   * 언어판을 영영 못 보게 된다(구글이 명시적으로 경고하는 패턴이고, 이 사이트는
   * 검색 유입이 핵심이다). 직접 /를 연 사람을 매번 튕겨내는 것도 성가시다.
   * 그래서 링크 하나를 제안하고, 선택은 사람이 한다.
   *
   * 한 번 고르거나 닫으면 다시 묻지 않는다 — 매 방문마다 뜨면 그게 곧 광고다. */
  var LANG_PREF_KEY = "lang-pref";

  function readLangPref() {
    // localStorage는 사파리 프라이빗 모드나 서드파티 차단 환경에서 접근만 해도
    // 예외를 던진다. 안내 배너 하나 때문에 아래 스크립트가 통째로 죽으면 안 된다.
    try {
      return window.localStorage.getItem(LANG_PREF_KEY);
    } catch (e) {
      return null;
    }
  }

  function writeLangPref(value) {
    try {
      window.localStorage.setItem(LANG_PREF_KEY, value);
    } catch (e) {
      /* 저장이 안 되면 다음 방문에 한 번 더 뜬다. 그 정도는 감수한다. */
    }
  }

  function prefersKorean() {
    var list = navigator.languages && navigator.languages.length
      ? navigator.languages
      : [navigator.language || ""];
    // "ko", "ko-KR" 은 맞고 "kok"(콘칸어) 같은 건 아니다. 접두사만 보면 안 된다.
    return /^ko(-|$)/i.test(String(list[0] || ""));
  }

  var langSuggest = document.getElementById("lang-suggest");
  if (langSuggest) {
    var pageLang = currentLang();
    var wantsKo = prefersKorean();
    // 이 페이지 언어가 브라우저가 원하는 언어와 다를 때만 안내한다.
    var mismatched = pageLang === "ko" ? !wantsKo : wantsKo;

    if (mismatched && !readLangPref()) {
      langSuggest.hidden = false;
    }

    var suggestLink = document.getElementById("lang-suggest-link");
    if (suggestLink) {
      suggestLink.addEventListener("click", function () {
        // 건너간 쪽이 이 사람의 선택이다. 그쪽 페이지에서 반대 방향으로 다시 묻지 않는다.
        writeLangPref(pageLang === "ko" ? "en" : "ko");
      });
    }
    var suggestClose = document.getElementById("lang-suggest-close");
    if (suggestClose) {
      suggestClose.addEventListener("click", function () {
        writeLangPref(pageLang);
        langSuggest.hidden = true;
      });
    }
  }

  // 상단 EN/한국어 스위치를 직접 누른 것도 명시적인 선택이다 — 그 뒤로는 안내하지 않는다.
  var langSwitch = document.querySelector(".lang-switch");
  if (langSwitch) {
    langSwitch.addEventListener("click", function () {
      writeLangPref(currentLang() === "ko" ? "en" : "ko");
    });
  }

  /* ---------- 용어사전: 목록 검색 ---------- */
  var glossarySearch = document.getElementById("glossary-search-input");
  var glossaryList = document.getElementById("glossary-list");
  if (glossarySearch && glossaryList) {
    // 전체 목록이 이미 서버에서 렌더링돼 있어(fetch 불필요) data-search 속성과
    // 단순 부분 문자열 비교만 하면 된다.
    var glossaryTerms = Array.prototype.slice.call(glossaryList.querySelectorAll(".glossary-term"));
    glossarySearch.addEventListener("input", function () {
      var q = glossarySearch.value.trim().toLowerCase();
      glossaryTerms.forEach(function (el) {
        var haystack = el.getAttribute("data-search") || "";
        el.hidden = q.length > 0 && haystack.indexOf(q) === -1;
      });
    });
  }

  /* ---------- 아카이브 검색 ---------- */
  var searchInput = document.getElementById("archive-search-input");
  var searchResults = document.getElementById("archive-search-results");
  if (searchInput && searchResults) {
    // 정적 인덱스는 이제 /api/search가 실패했을 때만 받는다. 예전에는 검색창에
    // 포커스가 가는 순간 무조건 내려받아서, 아카이브가 쌓일수록 그 자체가 부담이었다.
    var searchIndexPromise = null;
    var loadSearchIndex = function () {
      if (!searchIndexPromise) {
        searchIndexPromise = fetch(config.assetPrefix + "search-index.json")
          .then(function (r) {
            return r.json();
          })
          .catch(function () {
            return [];
          });
      }
      return searchIndexPromise;
    };
    var escapeHtml = function (s) {
      return String(s).replace(/[&<>"']/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
      });
    };
    var render = function (matches) {
      searchResults.innerHTML = matches
        .map(function (item) {
          var href = config.archivePrefix + item.date + ".html";
          return (
            '<li><a href="' + escapeHtml(href) + '">' + escapeHtml(item.title) + "</a>" +
            '<span class="archive-search-date">' + escapeHtml(item.date) + " · " + escapeHtml(item.source) + "</span></li>"
          );
        })
        .join("");
      searchResults.hidden = matches.length === 0;
    };

    // 정적 인덱스 폴백. /api/search가 죽어도 검색이 통째로 멈추지는 않게 한다 —
    // 다만 이 인덱스는 이제 폴백 전용이라 최근 며칠치만 담고 있어서, 결과 범위가
    // 서버 검색보다 좁다(정상 경로에서는 아예 내려받지 않는다).
    var searchStatic = function (q) {
      return loadSearchIndex().then(function (data) {
        var needle = q.toLowerCase();
        return data
          .filter(function (item) {
            var haystack = (
              (item.title || "") + " " + (item.summary_ko || "") + " " + (item.summary_en || "")
            ).toLowerCase();
            return haystack.indexOf(needle) !== -1;
          })
          .slice(0, 20);
      });
    };

    // 입력이 빠르면 이전 요청의 응답이 나중에 도착해 최신 결과를 덮어쓸 수 있다.
    // 매 검색에 번호를 매겨 가장 마지막 것만 그리게 한다.
    var searchSeq = 0;
    var runSearch = function () {
      var q = searchInput.value.trim();
      if (!q) {
        searchResults.hidden = true;
        searchResults.innerHTML = "";
        return;
      }
      var seq = ++searchSeq;
      searchResults.hidden = false;
      searchResults.innerHTML =
        '<li class="archive-search-loading">' +
        '<span class="lang-ko">불러오는 중...</span><span class="lang-en">Loading...</span></li>';

      // 절대경로로 고정한다. 서버리스 함수는 항상 /api/search 한 곳에만 있는데,
      // 상대경로로 쓰면 페이지 깊이(cleanUrls가 만드는 /topics 같은 형태 포함)에
      // 따라 /archive/api/search처럼 엉뚱한 곳을 가리킬 수 있다.
      fetch("/api/search?q=" + encodeURIComponent(q))
        .then(function (r) {
          if (!r.ok) throw new Error("search failed");
          return r.json();
        })
        .then(function (data) {
          return (data && data.results) || [];
        })
        .catch(function () {
          return searchStatic(q);
        })
        .then(function (matches) {
          if (seq !== searchSeq) return; // 더 최신 검색이 이미 시작됐다
          render(matches);
        });
    };
    // 키 입력마다 요청을 보내지 않도록 디바운스를 둔다.
    var searchTimer = null;
    searchInput.addEventListener("input", function () {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(runSearch, 200);
    });

    // ?q=... 로 들어오면 바로 검색한다. WebSite JSON-LD의 SearchAction이 이 주소
    // 형식을 가리키므로 실제로 동작해야 한다 — 없는 기능을 구조화 데이터로
    // 선언하면 안 된다. 덕분에 검색 결과를 링크로 공유할 수도 있다.
    try {
      var initialQuery = new URLSearchParams(window.location.search).get("q");
      if (initialQuery) {
        searchInput.value = initialQuery;
        runSearch();
      }
    } catch (e) {}
    document.addEventListener("click", function (e) {
      if (e.target !== searchInput && !searchResults.contains(e.target)) {
        searchResults.hidden = true;
      }
    });
  }

})();
