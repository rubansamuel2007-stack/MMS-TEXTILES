document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".flash").forEach(el => {
    setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 400); }, 4500);
  });
});
