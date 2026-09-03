const form = document.querySelector("#request-form");
const message = document.querySelector("#form-message");

form.addEventListener("submit", async function (event) {
  event.preventDefault();

  const submitButton = form.querySelector('button[type="submit"]');
  const originalButtonText = submitButton.textContent;
  submitButton.disabled = true;
  submitButton.textContent = "Отправка...";

  const formData = new FormData(form);
  const lead = Object.fromEntries(formData.entries());

  try {
    const response = await fetch("/api/leads", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(lead),
    });

    if (response.status === 422) {
      message.textContent = "Проверьте правильность заполнения формы.";
      return;
    }

    const result = await response.json();

    if (!response.ok || !result.success) {
      throw new Error("Сервер не принял заявку");
    }

    message.textContent = result.duplicate
      ? "Эта заявка уже была отправлена. Мы скоро свяжемся с вами."
      : "Спасибо! Заявка отправлена.";
    form.reset();
  } catch (error) {
    message.textContent = "Не удалось отправить заявку. Попробуйте ещё раз.";
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = originalButtonText;
  }
});
