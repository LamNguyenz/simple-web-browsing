button = document.querySelectorAll("#button")[0];

attr = button.getAttribute("value");
button.innerHTML = "Click me to get thing";

button.addEventListener("click", function (e) {
  console.log("You clicked the button");
});
