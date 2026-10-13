/* Career Radar frontend — dependency-free. Reads web/data/jobs.json. */
(function () {
  "use strict";

  var DATA_URL = "data/jobs.json";
  var PAGE = 60;

  var state = {
    jobs: [],
    meta: null,
    shown: PAGE,
    country: "",
    q: "",
    goal: "",
    spon: "",
    sort: "new",
    fresh: "",
  };

  var $ = function (id) { return document.getElementById(id); };
  var resultsEl = $("results"), moreBtn = $("more");

  var SYM = { USD: "$", GBP: "£", EUR: "€", INR: "₹" };

  function fmtMoney(cur, v) {
    if (v == null) return "";
    var sym = SYM[cur];
    if (cur === "INR" && v >= 100000) {
      var l = v / 100000;
      return "₹" + (l >= 100 ? Math.round(l) : (Math.round(l * 10) / 10)) + "L";
    }
    var k = v / 1000;
    var num = k >= 100 ? String(Math.round(k)) : String(Math.round(k * 10) / 10);
    return (sym || (cur + " ")) + num + "k";
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
      return '<span class="badge goal-yes" title="Disclosed pay meets the ₹5L/month savings target for ' +
        esc(j.country) + '">Meets savings goal</span>';
    if (j.goal === false)
      return '<span class="badge goal-no" title="Disclosed pay is below the savings target">Below goal</span>';
    return '<span class="badge goal-unknown" title="No salary disclosed in the posting">Salary not disclosed</span>';
  }

  function sponBadge(j) {
    if (j.spon === "yes")
      return '<span class="badge spon-yes" title="Posting mentions visa sponsorship">Sponsorship mentioned</span>';
    if (j.spon === "no")
      return '<span class="badge spon-no" title="Posting says no sponsorship">No sponsorship</span>';
    return "";
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
        '<p class="loc">' + esc(j.city) + " · " + esc(j.country) + "</p>" +
        '<div class="badges">' + goalBadge(j) + sponBadge(j) + "</div>" +
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
      if (state.country && j.country !== state.country) return false;
      if (state.goal === "yes" && j.goal !== true) return false;
      if (state.goal === "no" && j.goal !== false) return false;
      if (state.goal === "unknown" && j.goal != null) return false;
      if (state.spon && j.spon !== state.spon) return false;
      if (state.fresh) {
        var cutoff = Date.now() - parseInt(state.fresh, 10) * 864e5;
        var pt = Date.parse(j.pub || "");
        if (isNaN(pt) || pt < cutoff) return false;
      }
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
      : '<div class="empty">No jobs match these filters. Try widening the country or clearing the search.</div>';
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
    var sel = $("country");
    m.countries.forEach(function (c) {
      var o = document.createElement("option");
      o.value = c;
      o.textContent = c;
      sel.appendChild(o);
    });
    var th = $("thresholds");
    if (th && m.thresholds) {
      th.innerHTML = m.countries
        .map(function (c) {
          var cur = { India: "INR", "United Kingdom": "GBP",
            UAE: "AED", "Saudi Arabia": "SAR", Kuwait: "KWD",
            Canada: "CAD", Netherlands: "EUR", "New Zealand": "NZD",
            Poland: "PLN" }[c];
          var v = m.thresholds[c];
          return "<div><b>" + esc(c) + "</b>" + esc(cur) + " " +
            Number(v).toLocaleString("en-US") + " / yr</div>";
        })
        .join("");
    }
  }

  function bind() {
    $("country").addEventListener("change", function (e) {
      state.country = e.target.value; state.shown = PAGE; render();
    });
    $("goal").addEventListener("change", function (e) {
      state.goal = e.target.value; state.shown = PAGE; render();
    });
    $("spon").addEventListener("change", function (e) {
      state.spon = e.target.value; state.shown = PAGE; render();
    });
    $("fresh").addEventListener("change", function (e) {
      state.fresh = e.target.value; state.shown = PAGE; render();
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
    })
    .catch(function (err) {
      resultsEl.innerHTML =
        '<div class="empty">Could not load job data (' + esc(err.message) +
        "). Please try again later.</div>";
    });
})();
