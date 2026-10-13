/* Career Radar — India portal frontend. Dependency-free. Reads india/jobs.json. */
(function () {
  "use strict";

  var DATA_URL = "jobs.json";
  var PAGE = 60;

  var state = {
    jobs: [],
    meta: null,
    shown: PAGE,
    city: "",
    q: "",
    goal: "",
    sort: "new",
  };

  var $ = function (id) { return document.getElementById(id); };
  var resultsEl = $("results"), moreBtn = $("more");

  function fmtMoney(cur, v) {
    if (v == null) return "";
    if (cur === "INR" && v >= 100000) {
      var l = v / 100000;
      return "₹" + (l >= 100 ? Math.round(l) : (Math.round(l * 10) / 10)) + "L";
    }
    return "₹" + Math.round(v / 1000) + "k";
  }

  function salaryText(j) {
    if (j.smin == null || j.smax == null) return null;
    if (j.smin === j.smax) return fmtMoney(j.cur, j.smax);
    return fmtMoney(j.cur, j.smin) + " – " + fmtMoney(j.cur, j.smax);
  }

  function relTime(iso) {
    if (!iso) return "date unknown";
    var then = new Date(iso).getTime();
    var diff = Date.now() - then;
    if (isNaN(then) || diff < 0) return "date unknown";
    var m = Math.floor(diff / 60000);
    if (m < 1) return "just now";
    if (m < 60) return m + (m === 1 ? " min ago" : " mins ago");
    var h = Math.floor(m / 60);
    if (h < 24) return h + (h === 1 ? " hour ago" : " hours ago");
    var d = Math.floor(h / 24);
    if (d < 30) return d + (d === 1 ? " day ago" : " days ago");
    var mo = Math.floor(d / 30);
    return mo + (mo === 1 ? " month ago" : " months ago");
  }

  function goalBadge(j) {
    if (j.goal === true)
      return '<span class="badge goal-yes" title="Disclosed pay meets the ₹5L/month savings target">Meets savings goal</span>';
    if (j.goal === false)
      return '<span class="badge goal-no" title="Disclosed pay is below the savings target">Below goal</span>';
    return '<span class="badge goal-unknown" title="No salary disclosed in the posting">Salary not disclosed</span>';
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function card(j) {
    var sal = salaryText(j);
    return (
      '<article class="card">' +
        "<h3><a href=\"" + esc(j.url) + '" target="_blank" rel="noopener">' +
        esc(j.t) + "</a></h3>" +
        '<p class="company">' + esc(j.co) + "</p>" +
        '<p class="loc">' + esc(j.city) + " · India</p>" +
        '<div class="badges">' + goalBadge(j) + "</div>" +
        (sal ? '<p class="salary">' + esc(sal) + ' <small>/ year</small></p>' : "") +
        '<div class="foot"><span title="' + esc(j.pub || "") + '">' +
        esc(relTime(j.pub)) + '</span><a class="apply" href="' + esc(j.url) +
        '" target="_blank" rel="noopener">Apply →</a></div>' +
      "</article>"
    );
  }

  function filtered() {
    var q = state.q.trim().toLowerCase();
    var out = state.jobs.filter(function (j) {
      if (state.city && j.city !== state.city) return false;
      if (state.goal === "yes" && j.goal !== true) return false;
      if (state.goal === "no" && j.goal !== false) return false;
      if (state.goal === "unknown" && j.goal != null) return false;
      if (q && (j.t + " " + j.co).toLowerCase().indexOf(q) === -1) return false;
      return true;
    });
    if (state.sort === "salary") {
      out.sort(function (a, b) {
        var av = a.smax == null ? -1 : a.smax,
          bv = b.smax == null ? -1 : b.smax;
        return bv - av;
      });
    } else {
      out.sort(function (a, b) {
        return (b.pub || "").localeCompare(a.pub || "");
      });
    }
    return out;
  }

  function render() {
    var list = filtered();
    var slice = list.slice(0, state.shown);
    resultsEl.innerHTML = slice.length
      ? slice.map(card).join("")
      : '<div class="empty">No jobs match these filters. Try widening the city or clearing the search.</div>';
    moreBtn.hidden = list.length <= state.shown;
    moreBtn.textContent = "Show more (" + (list.length - state.shown) + " remaining)";
    $("count").textContent = list.length + (list.length === 1 ? " job" : " jobs");
  }

  function renderMeta() {
    var m = state.meta;
    if (!m) return;
    if (m.refreshed_at) {
      var el = $("refreshed");
      el.textContent = "listings refreshed " + relTime(m.refreshed_at);
      el.title = new Date(m.refreshed_at).toLocaleString();
    }
    var sel = $("city");
    (m.cities || []).forEach(function (c) {
      var o = document.createElement("option");
      o.value = c;
      o.textContent = c;
      sel.appendChild(o);
    });
    var th = $("thresholds");
    if (th && m.thresholds && m.thresholds.India) {
      th.innerHTML =
        "<div><b>India</b>₹" + Number(m.thresholds.India).toLocaleString("en-IN") + " / yr</div>";
    }
  }

  function bind() {
    $("city").addEventListener("change", function (e) {
      state.city = e.target.value; state.shown = PAGE; render();
    });
    $("goal").addEventListener("change", function (e) {
      state.goal = e.target.value; state.shown = PAGE; render();
    });
    $("sort").addEventListener("change", function (e) {
      state.sort = e.target.value; state.shown = PAGE; render();
    });
    var deb;
    $("search").addEventListener("input", function (e) {
      clearTimeout(deb);
      deb = setTimeout(function () {
        state.q = e.target.value; state.shown = PAGE; render();
      }, 180);
    });
    moreBtn.addEventListener("click", function () {
      state.shown += PAGE;
      render();
    });
    // refresh relative times every minute
    setInterval(function () {
      if (state.meta) {
        $("refreshed").textContent =
          "listings refreshed " + relTime(state.meta.refreshed_at);
      }
      render();
    }, 60000);
  }

  fetch(DATA_URL, { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (d) {
      state.jobs = d.jobs || [];
      state.meta = d.meta || null;
      renderMeta();
      bind();
      render();
      if (state.meta && state.meta.error && state.jobs.length === 0) {
        resultsEl.innerHTML =
          '<div class="empty">India listings are temporarily unavailable — ' +
          esc(state.meta.error) + "</div>";
      }
    })
    .catch(function (err) {
      resultsEl.innerHTML =
        '<div class="empty">Could not load job data (' + esc(err.message) +
        "). Please try again later.</div>";
    });
})();
