(function () {
  const slides = Array.from(document.querySelectorAll(".slide"));
  const count = document.getElementById("count");
  let index = 0;

  function show(next) {
    if (slides.length === 0) return;
    index = (next + slides.length) % slides.length;
    slides.forEach(function (slide, i) {
      slide.classList.toggle("on", i === index);
    });
    if (count) {
      count.textContent = String(index + 1) + " / " + String(slides.length);
    }
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "ArrowRight" || event.key === " " || event.key === "PageDown") {
      event.preventDefault();
      show(index + 1);
    }
    if (event.key === "ArrowLeft" || event.key === "PageUp") {
      event.preventDefault();
      show(index - 1);
    }
  });

  show(0);
})();
