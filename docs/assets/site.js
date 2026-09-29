document.documentElement.classList.add("js");
const menu = document.querySelector(".menu-button");
const sidebar = document.querySelector(".sidebar");
menu.addEventListener("click", () => {
  const expanded = menu.getAttribute("aria-expanded") !== "true";
  menu.setAttribute("aria-expanded", String(expanded));
  sidebar.classList.toggle("open", expanded);
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && sidebar.classList.contains("open")) {
    sidebar.classList.remove("open");
    menu.setAttribute("aria-expanded", "false");
    menu.focus();
  }
});
const status = document.querySelector(".copy-status");
let statusTimer;
document.querySelectorAll("pre").forEach(pre => {
  const code = pre.querySelector("code");
  if (!code) return;
  const wrapper = document.createElement("div");
  wrapper.className = "code-block";
  pre.before(wrapper);
  wrapper.append(pre);
  const label = document.createElement("span");
  label.className = "code-label";
  label.textContent = (code.className.match(/language-(\w+)/) || [null, "code"])[1];
  wrapper.append(label);
  if (!navigator.clipboard) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "copy-button";
  button.textContent = "Copy";
  button.setAttribute("aria-label", `Copy ${label.textContent} code`);
  wrapper.append(button);
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(code.textContent);
      status.textContent = "Code copied to clipboard";
      button.textContent = "Copied";
    } catch {
      status.textContent = "Copy unavailable. Select the code and copy it manually.";
    }
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => { status.textContent = ""; }, 2500);
    setTimeout(() => { button.textContent = "Copy"; }, 2000);
  });
});
document.querySelectorAll("table").forEach(table => {
  if (table.parentElement.classList.contains("table-wrap")) return;
  const wrapper = document.createElement("div");
  wrapper.className = "table-wrap";
  wrapper.tabIndex = 0;
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-label", "Scrollable reference table");
  table.before(wrapper);
  wrapper.append(table);
});
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(entries => {
    const visible = entries.find(entry => entry.isIntersecting);
    if (!visible) return;
    document.querySelectorAll(".toc a").forEach(link => {
      link.classList.toggle("active", link.hash === `#${visible.target.id}`);
    });
  }, { rootMargin: "-80px 0px -60% 0px" });
  document.querySelectorAll("article h2[id]").forEach(heading => observer.observe(heading));
}
