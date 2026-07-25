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

  /* ---------- 언어에 따라 placeholder 문구 교체 ---------- */
  function updatePlaceholders() {
    var lang = currentLang();
    Array.prototype.forEach.call(document.querySelectorAll("[data-placeholder-ko]"), function (el) {
      var attr = lang === "en" ? "data-placeholder-en" : "data-placeholder-ko";
      el.setAttribute("placeholder", el.getAttribute(attr) || "");
    });
  }
  updatePlaceholders();

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

  /* ---------- 언어 적용 (선택 시 / bfcache 복원 시 공용) ---------- */
  function applyLang(lang) {
    root.setAttribute("data-lang", lang);
    root.setAttribute("lang", lang);
    var titleAttr = lang === "en" ? "data-title-en" : "data-title-ko";
    var stored = root.getAttribute(titleAttr);
    if (stored) document.title = stored;
    updatePlaceholders();
  }

  /* ---------- bfcache 복원 시 테마/언어 재동기화 ----------
   * 뒤로가기/앞으로가기로 브라우저가 페이지를 bfcache에서 그대로 복원하면
   * (pageshow의 persisted===true) 스크립트가 다시 실행되지 않아 테마/언어가 "이 페이지를
   * 떠날 때의 상태"로 얼어붙는다 — 용어사전에서 언어를 바꾼 뒤 뒤로가기하면 기사 페이지가
   * 예전 언어로 보이던 문제. persisted 복원 시에만 저장된 값으로 다시 맞춘다. */
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    var t = getCookie("theme");
    if (t === "dark" || t === "light") {
      root.setAttribute("data-theme", t);
      if (themeBtn) themeBtn.setAttribute("aria-checked", String(t === "dark"));
    }
    try {
      if (config.defaultLang === "en") {
        // 영어권 착지 페이지는 저장된 선호와 무관하게 항상 영어로 유지한다.
        localStorage.setItem("lang", "en");
      } else {
        var l = localStorage.getItem("lang");
        if (l === "ko" || l === "en") applyLang(l);
      }
    } catch (err) {
      /* localStorage 차단 환경 — 테마만 복원하고 넘어간다 */
    }
    updatePlaceholders();
  });

  /* ---------- 한국어/영어 선택 드롭다운 ---------- */
  var langSelect = document.getElementById("lang-select");
  var langTrigger = document.getElementById("lang-select-trigger");
  var langList = document.getElementById("lang-select-list");
  if (langSelect && langTrigger && langList) {
    var langOptions = Array.prototype.slice.call(langList.querySelectorAll("li[data-lang-value]"));
    var closeList = function (returnFocus) {
      langList.hidden = true;
      langTrigger.setAttribute("aria-expanded", "false");
      if (returnFocus) langTrigger.focus();
    };
    var openList = function (focusIndex) {
      langList.hidden = false;
      langTrigger.setAttribute("aria-expanded", "true");
      if (typeof focusIndex === "number" && langOptions[focusIndex]) langOptions[focusIndex].focus();
    };
    var markSelected = function (lang) {
      langOptions.forEach(function (li) {
        li.setAttribute("aria-selected", String(li.getAttribute("data-lang-value") === lang));
      });
    };
    var selectLang = function (next) {
      applyLang(next);
      try {
        localStorage.setItem("lang", next);
      } catch (e) {
        /* 저장 실패해도 이번 페이지에는 이미 적용됐다 */
      }
      markSelected(next);
      closeList(true);
    };
    markSelected(currentLang());
    langTrigger.addEventListener("click", function (e) {
      e.stopPropagation();
      if (langList.hidden) openList();
      else closeList();
    });
    langTrigger.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        openList(e.key === "ArrowDown" ? 0 : langOptions.length - 1);
      }
    });
    // 옵션이 2개뿐이라 풀 콤보박스 패턴 대신 화살표(이동)+Enter/Space(선택)+Escape(닫기)만 지원.
    langOptions.forEach(function (li, i) {
      li.addEventListener("click", function () {
        selectLang(li.getAttribute("data-lang-value"));
      });
      li.addEventListener("keydown", function (e) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          langOptions[(i + 1) % langOptions.length].focus();
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          langOptions[(i - 1 + langOptions.length) % langOptions.length].focus();
        } else if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectLang(li.getAttribute("data-lang-value"));
        } else if (e.key === "Escape") {
          closeList(true);
        }
      });
    });
    document.addEventListener("click", function (e) {
      if (!langSelect.contains(e.target)) closeList();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeList();
    });
    // 포커스가 드롭다운 밖으로 나가면 닫는다(Tab으로 빠져나가는 경우).
    langSelect.addEventListener("focusout", function (e) {
      if (!langSelect.contains(e.relatedTarget)) closeList();
    });
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
    var setStatus = function (key) {
      subscribeStatus.textContent = messages[key][currentLang()];
    };
    subscribeForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var input = subscribeForm.querySelector('input[name="email"]');
      var submitBtn = subscribeForm.querySelector(".subscribe-submit");
      var email = input.value.trim();
      submitBtn.disabled = true;
      setStatus("sending");
      fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email })
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
      termBackdrop.hidden = false;
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
      if (termTrigger) {
        termTrigger.focus();
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
    var searchIndexPromise = null;
    var indexLoaded = false;
    var loadSearchIndex = function () {
      if (!searchIndexPromise) {
        searchIndexPromise = fetch(config.assetPrefix + "search-index.json")
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            indexLoaded = true;
            return data;
          })
          .catch(function () {
            indexLoaded = true;
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
    var runSearch = function () {
      var q = searchInput.value.trim().toLowerCase();
      if (!q) {
        searchResults.hidden = true;
        searchResults.innerHTML = "";
        return;
      }
      // 인덱스를 아직 못 불러온 상태에서 입력하면, fetch가 끝나기 전까지 잠깐이라도
      // "결과 없음"으로 오인되지 않도록 로딩 상태를 먼저 보여준다.
      if (!indexLoaded) {
        searchResults.hidden = false;
        searchResults.innerHTML =
          '<li class="archive-search-loading">' +
          '<span class="lang-ko">불러오는 중...</span><span class="lang-en">Loading...</span></li>';
      }
      loadSearchIndex().then(function (data) {
        var matches = data
          .filter(function (item) {
            var haystack = (
              (item.title || "") + " " + (item.summary_ko || "") + " " + (item.summary_en || "")
            ).toLowerCase();
            return haystack.indexOf(q) !== -1;
          })
          .slice(0, 20);
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
      });
    };
    // 인덱스는 날마다 커지고 매 키 입력마다 전체를 훑으므로 디바운스를 둔다.
    var searchTimer = null;
    searchInput.addEventListener("focus", loadSearchIndex);
    searchInput.addEventListener("input", function () {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(runSearch, 120);
    });
    document.addEventListener("click", function (e) {
      if (e.target !== searchInput && !searchResults.contains(e.target)) {
        searchResults.hidden = true;
      }
    });
  }

  /* ---------- 용어 지도 (용어사전 페이지의 연결 그래프) ----------
   * 누적된 용어들을 서로 밀어내면서(반발력) 연관 있는 것끼리는 당기고(스프링), 노드마다
   * 다른 주기의 사인파로 부유시키는 아주 단순한 force-directed 레이아웃. 외부 라이브러리
   * 없이 매 프레임 위치만 갱신하고, 노드는 일반 <button>이라 클릭/포커스/스크린리더가
   * 그대로 동작한다 — 이 그래프는 아래 목록의 시각적 보조 수단일 뿐이라 실패해도
   * 정보 손실이 없다. */
  var graphWrap = document.getElementById("glossary-graph");
  var graphDataEl = document.getElementById("glossary-graph-data");
  if (graphWrap && graphDataEl) {
    var graphData = {};
    try {
      graphData = JSON.parse(graphDataEl.textContent || "{}");
    } catch (e) {
      graphData = {};
    }
    var gNodes = graphData.nodes || [];
    var gEdges = graphData.edges || [];

    if (gNodes.length >= 2) {
      var svgNS = "http://www.w3.org/2000/svg";
      var edgesSvg = document.getElementById("glossary-graph-edges");
      var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      var W = 0;
      var H = 0;
      var margin = 0;
      var nodeState = gNodes.map(function (n) {
        return {
          term: n.term,
          x: 0, y: 0, vx: 0, vy: 0, renderX: 0, renderY: 0,
          // 노드마다 주기·위상·진폭을 달리해 같은 리듬으로 움직이지 않게 한다.
          floatFreqX: 0.35 + Math.random() * 0.35,
          floatFreqY: 0.35 + Math.random() * 0.35,
          floatPhaseX: Math.random() * Math.PI * 2,
          floatPhaseY: Math.random() * Math.PI * 2,
          floatAmp: 8 + Math.random() * 6
        };
      });

      var indexByTerm = {};
      nodeState.forEach(function (n, i) {
        indexByTerm[n.term] = i;
      });
      var edgePairs = gEdges
        .map(function (e) {
          return [indexByTerm[e[0]], indexByTerm[e[1]]];
        })
        .filter(function (p) {
          return p[0] !== undefined && p[1] !== undefined;
        });

      var nodeEls = gNodes.map(function (n) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "glossary-node";
        btn.setAttribute("data-term", n.term);
        var koSpan = document.createElement("span");
        koSpan.className = "lang-ko";
        koSpan.textContent = n.label_ko;
        var enSpan = document.createElement("span");
        enSpan.className = "lang-en";
        enSpan.textContent = n.label_en;
        btn.appendChild(koSpan);
        btn.appendChild(enSpan);
        btn.addEventListener("click", function () {
          var entry = glossaryData[n.term];
          if (entry) openTermPanel(n.term, entry, btn);
        });
        graphWrap.appendChild(btn);
        return btn;
      });

      var lineEls = edgePairs.map(function () {
        var line = document.createElementNS(svgNS, "line");
        line.setAttribute("class", "glossary-graph-line");
        edgesSvg.appendChild(line);
        return line;
      });

      // 컨테이너 크기가 바뀌면(회전, 창 크기 조절) 좌표계를 다시 잡는다.
      var layout = function () {
        W = graphWrap.clientWidth || 600;
        H = graphWrap.clientHeight || 320;
        edgesSvg.setAttribute("viewBox", "0 0 " + W + " " + H);
        // 좁은 화면에서도 알약이 잘리지 않게 여백을 크기에 비례해 잡되 최솟값을 둔다.
        margin = Math.max(36, Math.min(W, H) * 0.16);
        var radius = Math.min(W, H) * 0.32;
        nodeState.forEach(function (n, i) {
          var angle = (i / nodeState.length) * Math.PI * 2;
          n.x = W / 2 + Math.cos(angle) * radius;
          n.y = H / 2 + Math.sin(angle) * radius;
          n.vx = 0;
          n.vy = 0;
        });
      };

      var startTime = null;
      var settled = false;

      var step = function (elapsed) {
        // 평형에 도달하기 전까지만 물리 계산을 돌린다. 도달한 뒤에도 계속 O(n²)
        // 반발력을 60fps로 계산하면 정적인 페이지가 배터리만 먹는다.
        if (!settled) {
          var moved = 0;
          for (var i = 0; i < nodeState.length; i++) {
            for (var j = i + 1; j < nodeState.length; j++) {
              var a = nodeState[i];
              var b = nodeState[j];
              var dx = a.x - b.x;
              var dy = a.y - b.y;
              var distSq = dx * dx + dy * dy || 0.01;
              var dist = Math.sqrt(distSq);
              var force = 1800 / distSq;
              var fx = (dx / dist) * force;
              var fy = (dy / dist) * force;
              a.vx += fx; a.vy += fy;
              b.vx -= fx; b.vy -= fy;
            }
          }
          edgePairs.forEach(function (p) {
            var a = nodeState[p[0]];
            var b = nodeState[p[1]];
            var dx = b.x - a.x;
            var dy = b.y - a.y;
            var dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
            var target = Math.min(W, H) * 0.34;
            var f = (dist - target) * 0.02;
            var fx = (dx / dist) * f;
            var fy = (dy / dist) * f;
            a.vx += fx; a.vy += fy;
            b.vx -= fx; b.vy -= fy;
          });
          nodeState.forEach(function (n) {
            n.vx += (W / 2 - n.x) * 0.001;
            n.vy += (H / 2 - n.y) * 0.001;
            n.vx *= 0.85;
            n.vy *= 0.85;
            n.x += n.vx;
            n.y += n.vy;
            n.x = Math.max(margin, Math.min(W - margin, n.x));
            n.y = Math.max(margin, Math.min(H - margin, n.y));
            moved += Math.abs(n.vx) + Math.abs(n.vy);
          });
          if (moved / nodeState.length < 0.05) settled = true;
        }

        nodeState.forEach(function (n) {
          var ox = reduceMotion ? 0 : Math.sin(elapsed * n.floatFreqX + n.floatPhaseX) * n.floatAmp;
          var oy = reduceMotion ? 0 : Math.cos(elapsed * n.floatFreqY + n.floatPhaseY) * n.floatAmp;
          // 부유 오프셋이 가장자리 노드를 컨테이너 밖으로 밀어낼 수 있어(폭이 좁은
          // 모바일에서 특히) 화면에 그리는 좌표도 같은 여백 안으로 다시 가둔다.
          n.renderX = Math.max(margin, Math.min(W - margin, n.x + ox));
          n.renderY = Math.max(margin, Math.min(H - margin, n.y + oy));
        });
        nodeEls.forEach(function (btn, i) {
          btn.style.setProperty("--x", nodeState[i].renderX + "px");
          btn.style.setProperty("--y", nodeState[i].renderY + "px");
        });
        lineEls.forEach(function (line, i) {
          var a = nodeState[edgePairs[i][0]];
          var b = nodeState[edgePairs[i][1]];
          line.setAttribute("x1", a.renderX);
          line.setAttribute("y1", a.renderY);
          line.setAttribute("x2", b.renderX);
          line.setAttribute("y2", b.renderY);
        });
      };

      layout();

      if (reduceMotion) {
        // 모션을 원치 않는 사용자에게는 애니메이션 없이 최종 배치만 보여준다.
        for (var iter = 0; iter < 300 && !settled; iter++) step(0);
        step(0);
      } else {
        var rafId = null;
        var loop = function (now) {
          if (startTime === null) startTime = now || 0;
          step(((now || 0) - startTime) / 1000);
          rafId = window.requestAnimationFrame(loop);
        };
        var start = function () {
          if (rafId === null) rafId = window.requestAnimationFrame(loop);
        };
        var stop = function () {
          if (rafId !== null) {
            window.cancelAnimationFrame(rafId);
            rafId = null;
          }
        };
        start();
        document.addEventListener("visibilitychange", function () {
          if (document.hidden) {
            stop();
          } else {
            startTime = null;
            start();
          }
        });
        var resizeTimer = null;
        window.addEventListener("resize", function () {
          if (resizeTimer) clearTimeout(resizeTimer);
          resizeTimer = setTimeout(function () {
            settled = false; // 새 크기에 맞춰 다시 자리를 잡는다
            layout();
          }, 150);
        });
      }
    }
  }
})();
