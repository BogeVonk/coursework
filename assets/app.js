const API_BASE = window.API_BASE || (location.protocol === "file:" ? "http://127.0.0.1:8000" : `${location.protocol}//${location.hostname}:8000`);
const CART_KEY = "potolok_cart_v1";
const PRODUCT_IDS = {"spot-01":1,"spot-02":2,"spot-03":3,"lustre-01":4,"lustre-02":5,"lustre-03":6,"track-01":7,"track-02":8,"led-01":9,"led-02":10,"line-01":11,"line-02":12};

const money = value =>
  new Intl.NumberFormat("ru-RU").format(Math.round(value)) + " ₽";

const readCart = () => {
  try {
    return JSON.parse(localStorage.getItem(CART_KEY) || "[]");
  } catch {
    return [];
  }
};

const saveCart = cart => {
  localStorage.setItem(CART_KEY, JSON.stringify(cart));
  updateCartCount();
};

function updateCartCount() {
  const count = readCart().reduce((sum, item) => sum + item.qty, 0);
  document.querySelectorAll("[data-cart-count]").forEach(el => {
    el.textContent = count;
  });
}

function toast(message) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.append(el);
  }
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}

function addToCart(product, qty = 1) {
  const cart = readCart();
  const found = cart.find(item => item.id === product.id);
  if (found) {
    found.qty += qty;
  } else {
    cart.push({ ...product, qty });
  }
  saveCart(cart);
  toast("Товар добавлен в корзину");
}

function setupMenu() {
  const toggle = document.querySelector(".menu-toggle");
  const nav = document.querySelector(".main-nav");
  if (!toggle || !nav) return;

  toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });

  nav.querySelectorAll("a").forEach(link => {
    link.addEventListener("click", () => {
      nav.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    });
  });
}


function setupModal() {
  const modal = document.querySelector("#quoteModal");

  if (!modal) return;

  document.addEventListener("click", event => {
    const openButton = event.target.closest("[data-open-quote]");
    const closeButton = event.target.closest("[data-close-modal]");

    if (openButton) {
      modal.classList.add("open");
      document.body.classList.add("lock");
      modal.setAttribute("aria-hidden", "false");
    }

    if (closeButton) {
      modal.classList.remove("open");
      document.body.classList.remove("lock");
      modal.setAttribute("aria-hidden", "true");
    }
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      modal.classList.remove("open");
      document.body.classList.remove("lock");
      modal.setAttribute("aria-hidden", "true");
    }
  });
}


async function sendJSON(path, payload) {
  let response;
  try {
    response = await fetch(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch {
    throw new Error("Сервер временно недоступен. Проверьте запуск FastAPI.");
  }

  let data = {};
  try {
    data = await response.json();
  } catch {}

  if (!response.ok) {
    const error = new Error(typeof data.detail === "string" ? data.detail : data.detail?.message || "Не удалось отправить данные");
    error.detail = data.detail;
    throw error;
  }

  return data;
}


function setupQuoteForm() {
  const forms = document.querySelectorAll("#quoteForm");
  if (!forms.length) return;

  forms.forEach(form => {
    form.addEventListener("submit", async event => {
      event.preventDefault();

      const button = form.querySelector('[type="submit"]');
      const original = button.innerHTML;

      button.disabled = true;
      button.textContent = "Отправляем…";

      const formData = new FormData(form);

      const payload = {
        name: formData.get("name"),
        number_phone: formData.get("number_phone") || formData.get("phone"),
        email: formData.get("email") || "",
        area: Number(formData.get("area")),
        service: formData.get("services"),
        address: formData.get("address"),
        comment: formData.get("comment"),
        privacy_consent: formData.get("privacy_consent") === "on"
      };

      try {
        const applicationResult = await sendJSON("/applications/", payload);
        if (applicationResult?.id_application) {
          localStorage.setItem("potolok_last_application_id", String(applicationResult.id_application));
        }

        form.reset();

        const result = form.parentElement.querySelector(".form-result");

        if (result) {
          result.textContent =
            "Заявка успешно отправлена. Менеджер свяжется с вами.";
        }

        toast("Заявка отправлена");

      } catch (error) {
        toast(error.message + " Проверьте, запущен ли сервер.");
      } finally {
        button.disabled = false;
        button.innerHTML = original;
      }
    });
  });
}


function setupProductButtons() {
  document.querySelectorAll("[data-add-product]").forEach(btn => {
    btn.addEventListener("click", () => {
      const card = btn.closest("[data-product]");
      if (!card) return;
      addToCart(
        {
          id: card.dataset.id,
          productId: PRODUCT_IDS[card.dataset.id] || card.dataset.id,
          name: card.dataset.name,
          price: Number(card.dataset.price),
          image: card.dataset.image
        },
        1
      );
    });
  });
}

function renderCart() {
  const root = document.querySelector("#cartItems");
  if (!root) return;

  const cart = readCart();
  if (!cart.length) {
    root.innerHTML = `
      <div class="empty-state">
        <h3>Корзина пока пуста</h3>
        <p>Добавьте светильники или LED-ленту из каталога.</p>
        <a class="btn btn-dark" href="shop.html">Перейти в магазин</a>
      </div>
    `;
    document.querySelector("#cartTotal").textContent = money(0);
    return;
  }

  root.innerHTML = cart.map((item, index) => `
    <article class="cart-item">
      <img
        src="${escapeHTML(item.image || "")}" 
        alt="${escapeHTML(item.name)}"
        onerror="this.style.background='#eef1f6';this.style.width='90px';this.style.height='80px'"
      >
      <div>
        <h3>${escapeHTML(item.name)}</h3>
        <small>${money(item.price)} / шт.</small>
        <p>
          <label class="muted">
            Количество
            <input type="number" min="1" max="99" value="${item.qty}" data-qty="${index}">
          </label>
        </p>
      </div>
      <div>
        <b>${money(item.price * item.qty)}</b><br>
        <button class="remove-item" data-remove="${index}">Удалить</button>
      </div>
    </article>
  `).join("");

  document.querySelector("#cartTotal").textContent = money(
    cart.reduce((sum, item) => sum + item.price * item.qty, 0)
  );

  root.querySelectorAll("[data-qty]").forEach(input => {
    input.addEventListener("change", () => {
      const currentCart = readCart();
      currentCart[Number(input.dataset.qty)].qty = Math.max(1, Math.min(99, Number(input.value) || 1));
      saveCart(currentCart);
      renderCart();
    });
  });

  root.querySelectorAll("[data-remove]").forEach(btn => {
    btn.addEventListener("click", () => {
      const currentCart = readCart();
      currentCart.splice(Number(btn.dataset.remove), 1);
      saveCart(currentCart);
      renderCart();
    });
  });
}

function escapeHTML(str) {
  return String(str).replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[char]));
}


function setupCheckout() {
  const form = document.querySelector("#checkoutForm");
  if (!form) return;

  const deliverySelect = form.querySelector('[name="delivery"]');
  const applicationField = form.querySelector("#applicationChoiceField");
  const applicationInput = form.querySelector('[name="application_id"]');
  const addressField = form.querySelector("#deliveryAddressField");
  const addressInput = form.querySelector('[name="address"]');
  const carrierField = form.querySelector("#carrierField");
  const details = form.querySelector("#checkoutDetails");
  const resultElement = form.querySelector("#checkoutResult");
  const createApplicationHint = form.querySelector("#createApplicationHint");
  const syncApplicationField = () => {
    const isDelivery = deliverySelect.value === "delivery";
    applicationField.hidden = true;
    applicationInput.required = false;
    applicationInput.replaceChildren();
    addressField.hidden = !isDelivery;
    carrierField.hidden = !isDelivery;
    createApplicationHint.hidden = deliverySelect.value !== "installer";
    addressInput.required = isDelivery;
    details.textContent = isDelivery ? "Онлайн-оплата. Стоимость и сроки доставки менеджер уточнит после оформления." : "Стоимость товаров будет учтена вместе с заявкой. Укажите те же имя и телефон, что при её отправке.";
  };
  deliverySelect?.addEventListener("change", syncApplicationField);
  syncApplicationField();
  [form.elements.name, form.elements.number_phone].forEach(input => input.addEventListener("input", () => {
    applicationField.hidden = true;
    applicationInput.required = false;
    applicationInput.replaceChildren();
  }));

  form.addEventListener("submit", async event => {
    event.preventDefault();

    const cart = readCart();

    if (!cart.length) {
      toast("Корзина пуста");
      return;
    }

    const button = form.querySelector('[type="submit"]');
    button.disabled = true;

    try {
      const formData = new FormData(form);

      const payload = {
        name: formData.get("name"),
        number_phone: formData.get("number_phone"),
        email: formData.get("email") || "",
        address: formData.get("address"),
        comment: formData.get("comment"),
        items: cart.map(item => ({
          product_id: item.productId || PRODUCT_IDS[item.id] || item.id,
          name: item.name,
          quantity: item.qty,
          price: item.price
        })),
        total: cart.reduce(
          (sum, item) => sum + item.price * item.qty,
          0
        ),
        carrier: formData.get("carrier"),
        payment_method: formData.get("delivery") === "delivery" ? "online" : "with_application",
        privacy_consent: formData.get("privacy_consent") === "on"
      };

      payload.delivery = formData.get("delivery") || "delivery";
      if (payload.delivery === "installer") {
        if (formData.get("application_id")) payload.application_id = Number(formData.get("application_id"));
      }
      const result = await sendJSON("/orders/", payload);
      sessionStorage.setItem("potolok_checkout_preview", JSON.stringify(payload));
      localStorage.removeItem(CART_KEY);
      renderCart();
      updateCartCount();
      resultElement.textContent = `Заказ №${result.id_order} оформлен. Менеджер свяжется с вами.`;
      if (payload.payment_method === "online" && result.checkout_token) {
        try {
          const payment = await sendJSON(`/orders/${result.id_order}/payment`, {
            access_token: result.checkout_token,
            return_url: location.protocol === "file:" ? "http://localhost:5500/cart.html?payment=complete" : `${location.origin}${location.pathname}?payment=complete`
          });
          if (payment.status === "redirect" && payment.confirmation_url) {
            location.href = payment.confirmation_url;
            return;
          }
          resultElement.textContent = `Заказ №${result.id_order} оформлен. Онлайн-оплата пока не подключена, менеджер уточнит детали.`;
          toast(resultElement.textContent);
        } catch {
          toast(`Заказ №${result.id_order} оформлен. Менеджер свяжется для оплаты.`);
        }
      } else {
        toast(`Заказ №${result.id_order} оформлен`);
      }

    } catch (error) {
      if (error.detail?.code === "choose_application") {
        applicationInput.replaceChildren(...error.detail.applications.map(item => {
          const option = document.createElement("option");
          option.value = item.id;
          option.textContent = `${item.service} — ${item.address}`;
          return option;
        }));
        applicationField.hidden = false;
        applicationInput.required = true;
        resultElement.textContent = "Найдено несколько заявок. Выберите нужную и нажмите «Оформить заказ» ещё раз.";
        applicationInput.focus();
      } else {
        resultElement.textContent = error.message;
        toast(error.message);
      }
    } finally {
      button.disabled = false;
    }
  });
}


function stackCardsOnCompactScreens() {
  if (window.innerWidth <= 1100) {
    document.querySelectorAll(".grid-3, .grid-4").forEach(grid => {
      grid.style.gridTemplateColumns = "minmax(0, 1fr)";
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  stackCardsOnCompactScreens();
  setupMenu();
  setupModal();
  setupQuoteForm();
  setupProductButtons();
  renderCart();
  setupCheckout();
  updateCartCount();
  const checkoutPreview = sessionStorage.getItem("potolok_checkout_preview");
  if (new URLSearchParams(location.search).get("payment") === "complete" && checkoutPreview) {
    toast("Возвращаемся после оплаты. Заказ проверит менеджер.");
    history.replaceState({}, document.title, location.pathname);
  }
});
