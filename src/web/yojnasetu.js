/* Yojna Setu — custom elements.
 *
 * Light DOM on purpose: the shared stylesheet applies without piercing shadow
 * boundaries, and the markup stays inspectable in devtools during a demo.
 *
 * <av-card> renders one card from the chat API. The API decides WHAT to show
 * (its `kind`); this decides how it looks. That split is why WhatsApp and the
 * web can share an engine without sharing a presentation.
 */

export const esc = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/** Strip the WhatsApp *bold* markers used by the shared literacy copy. */
export const plain = s => String(s ?? "").replace(/[*_]/g, "");

class AvCard extends HTMLElement {
  set data(v) { this._d = v; if (this.isConnected) this.render(); }
  get data() { return this._d; }
  connectedCallback() { if (this._d) this.render(); }

  render() {
    const d = this._d;
    const L = window.AV_STRINGS || {};
    const s = k => L[k] || k;
    const box = (head, body, cls = "") =>
      `<div class="card ${cls}">${head ? `<div class="card-h">${esc(head)}</div>` : ""}
        <div class="card-b">${body}</div></div>`;

    switch (d.kind) {

      case "scheme":
        this.innerHTML = box("", `
          <div class="sch-top">
            <div class="sch-name">${esc(d.name)}</div>
            ${d.best ? `<span class="badge">${esc(s("cheapest"))}</span>` : ""}
          </div>
          <div class="sch-grid">
            <div><div class="k">${esc(s("it_costs"))}</div>
                 <div class="v big num">${esc(d.interest)}</div></div>
            <div><div class="k">${esc(d.rate)}% ${esc(s("per_year"))}</div>
                 <div class="v num">${esc(d.loan)}</div></div>
            <div><div class="k">${esc(s("quarterly"))}</div>
                 <div class="v num">${esc(d.instalment)}</div></div>
            <div><div class="k">${esc(s("you_repay"))}</div>
                 <div class="v num">${esc(d.total)}</div></div>
          </div>
          <div class="sch-why">${esc(s("per_month_budget").replace("{amount}", d.monthly))}
            · ${esc(d.instalment_count)} × ${esc(s("quarterly"))}</div>`);
        break;

      case "compare": {
        const max = Math.max(d.scheme_raw, d.alt_raw) || 1;
        const w = v => Math.max(3, (v / max) * 100) + "%";
        this.innerHTML = box(s("card_compare"), `
          <div class="cmp-row">
            <div class="cmp-top"><span class="cmp-who">${esc(d.scheme_label)}</span>
              <span class="cmp-amt good num">${esc(d.scheme_amount)}</span></div>
            <div class="cmp-track"><div class="cmp-fill good"></div></div>
          </div>
          <div class="cmp-row">
            <div class="cmp-top"><span class="cmp-who">${esc(d.alt_label)}</span>
              <span class="cmp-amt bad num">${esc(d.alt_amount)}</span></div>
            <div class="cmp-track"><div class="cmp-fill bad"></div></div>
          </div>
          <div class="cmp-save">${esc(s("you_save"))} ${esc(d.saving)}</div>`);
        const f = this.querySelectorAll(".cmp-fill");
        requestAnimationFrame(() => {
          f[0].style.width = w(d.scheme_raw);
          f[1].style.width = w(d.alt_raw);
        });
        break;
      }

      case "partners":
        this.innerHTML = box(s("card_where"), d.items.map((p, i) => `
          <div class="row">
            <div class="rank">${i + 1}</div>
            <div class="body">
              <div class="name">${esc(p.name)}</div>
              <div class="sub">${esc(p.where)}
                ${p.official ? '<span class="tag ok">published data</span>'
                             : '<span class="tag q">representative</span>'}</div>
            </div>
            <div class="end"><div class="d num">${esc(p.distance_km)} ${esc(s("km_away"))}</div>
              <div class="r num">${esc(p.rate)}%</div></div>
          </div>`).join(""));
        break;

      case "map":
        this.innerHTML = `<div class="card"><img class="map" alt="Map of nearby offices"
          src="${esc(d.url)}"></div>`;
        break;

      case "whynot":
        this.innerHTML = box(s("card_whynot"), d.items.map(r => `
          <div class="row"><div class="dot warn"></div><div class="body">
            <div class="name">${esc(r.name)}</div>
            <div class="sub">${esc(r.reason)}</div></div></div>`).join(""));
        break;

      case "blocked":
        this.innerHTML = box(s("card_blocked"), d.items.map(r => `
          <div class="row"><div class="dot bad"></div><div class="body">
            <div class="name">${esc(r.name)}</div>
            <div class="sub">${esc(r.reason)}</div></div></div>`).join(""));
        break;

      case "rejection":
        this.innerHTML = box("", `<div class="row"><div class="dot warn"></div>
          <div class="body"><div class="name">${esc(d.name)}</div>
          <div class="sub">${esc(d.reason)}</div></div></div>`);
        break;

      case "notice":
        this.innerHTML = `<div class="notice ${esc(d.tone || "info")}">${esc(plain(d.body))}</div>`;
        break;

      default:
        this.innerHTML = "";
    }
  }
}

customElements.define("av-card", AvCard);
