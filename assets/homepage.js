document.addEventListener("DOMContentLoaded", () => {
  const container = document.querySelector("#roomsContainer");
  if (!container) return;

  const rates = {
    ceiling: {
      matte: 650,
      glossy: 700,
      satin: 750,
      fabric: 1500,
      floating: 1100,
      multi: 1400
    },
    lighting: {
      none: 0,
      spot: 350,
      track: 650,
      line: 1200
    },
    extras: {
      led: 450,
      curtain: 1800,
      pipe: 500,
      corners: 250
    }
  };

  const money = value =>
    new Intl.NumberFormat("ru-RU").format(Math.round(value)) + " ₽";

  let nextId = 0;

  const template = id => `
    <article class="room-card">
      <div class="room-card-head">
        <b>Помещение ${id + 1}</b>
        ${id ? '<button class="remove-room" type="button">Удалить</button>' : ""}
      </div>
      <div class="room-fields">
        <label>Название помещения
          <input data-f="name" maxlength="40" value="${id ? "Помещение" : "Комната"}">
        </label>
        <label>Тип потолка
          <select data-f="ceiling">
            <option value="matte">Матовый</option>
            <option value="glossy">Глянцевый</option>
            <option value="satin">Сатиновый</option>
            <option value="fabric">Тканевый</option>
            <option value="floating">Парящий</option>
            <option value="multi">Многоуровневый</option>
          </select>
        </label>
        <label>Площадь, м²
          <input data-f="area" type="number" min="1" max="500" step=".1" value="18">
        </label>
        <label>Количество углов
          <input data-f="corners" type="number" min="4" max="30" value="4">
        </label>
        <div class="room-subtitle">ОСВЕЩЕНИЕ</div>
        <label>Тип освещения
          <select data-f="lighting">
            <option value="none">Не требуется</option>
            <option value="spot">Точечные светильники</option>
            <option value="track">Трековое освещение</option>
            <option value="line">Световые линии</option>
          </select>
        </label>
        <label>Количество элементов
          <input data-f="lights" type="number" min="0" max="100" value="4">
        </label>
        <div class="room-subtitle">ДОПОЛНИТЕЛЬНЫЕ РАБОТЫ</div>
        <label class="room-check"><span><input data-f="led" type="checkbox"> LED-лента</span></label>
        <label class="room-check"><span><input data-f="curtain" type="checkbox"> Скрытый карниз</span></label>
        <label class="room-check"><span><input data-f="pipe" type="checkbox"> Обход трубы</span></label>
      </div>
    </article>
  `;

  function read(card) {
    const v = key => card.querySelector(`[data-f="${key}"]`);
    return {
      name: v("name").value.trim() || "Помещение",
      ceiling: v("ceiling").value,
      area: Math.max(0, +v("area").value || 0),
      corners: Math.max(0, +v("corners").value || 0),
      lighting: v("lighting").value,
      lights: Math.max(0, +v("lights").value || 0),
      led: v("led").checked,
      curtain: v("curtain").checked,
      pipe: v("pipe").checked
    };
  }

  function calc(room) {
    const lines = [
      ["Полотно и монтаж", room.area * rates.ceiling[room.ceiling]]
    ];
    if (room.lighting !== "none" && room.lights) {
      lines.push(["Освещение", rates.lighting[room.lighting] * room.lights]);
    }
    if (room.corners > 4) {
      lines.push(["Дополнительные углы", (room.corners - 4) * rates.extras.corners]);
    }
    if (room.led) {
      lines.push(["LED-лента", room.area * rates.extras.led * 0.25]);
    }
    if (room.curtain) {
      lines.push(["Скрытый карниз", rates.extras.curtain]);
    }
    if (room.pipe) {
      lines.push(["Обход трубы", rates.extras.pipe]);
    }
    return {
      lines,
      total: lines.reduce((sum, line) => sum + line[1], 0)
    };
  }

  function update() {
    const cards = [...container.querySelectorAll(".room-card")];
    const out = document.querySelector("#estimateBreakdown");
    out.innerHTML = "";
    let total = 0;

    cards.forEach((card, index) => {
      const room = read(card);
      const cost = calc(room);
      total += cost.total;

      const head = document.createElement("div");
      head.className = "estimate-line";
      head.innerHTML = `
        <b>${index + 1}. ${room.name.replace(/[<>]/g, "")}</b>
        <b>${money(cost.total)}</b>
      `;
      out.append(head);

      cost.lines.forEach(([label, value]) => {
        const row = document.createElement("div");
        row.className = "estimate-line";
        row.innerHTML = `<span>${label}</span><span>${money(value)}</span>`;
        out.append(row);
      });
    });

    document.querySelector("#estimateTotal").textContent = money(total);

    const count = cards.length;
    document.querySelector("#roomCounter").textContent =
      count + " " + (count === 1 ? "помещение" : count < 5 ? "помещения" : "помещений");
  }

  function add() {
    container.insertAdjacentHTML("beforeend", template(nextId++));
    update();
  }

  add();

  document.querySelector("#addRoom").addEventListener("click", () => {
    if (container.children.length >= 10) {
      alert("Можно добавить не более 10 помещений.");
      return;
    }
    add();
  });

  container.addEventListener("input", update);
  container.addEventListener("change", update);

  container.addEventListener("click", event => {
    const removeBtn = event.target.closest(".remove-room");
    if (!removeBtn) return;
    removeBtn.closest(".room-card").remove();
    [...container.querySelectorAll(".room-card-head b")].forEach((b, i) => {
      b.textContent = "Помещение " + (i + 1);
    });
    update();
  });

  document.querySelector("#calcRequest").addEventListener("click", () => {
    const rooms = [...container.querySelectorAll(".room-card")].map(read);
    const area = rooms.reduce((sum, room) => sum + room.area, 0);
    const comments = rooms
      .map((room, index) => {
        return `${index + 1}) ${room.name}: ${room.area} м², ${room.ceiling}, углов: ${room.corners}, освещение: ${room.lighting} (${room.lights}), LED: ${room.led ? "да" : "нет"}, карниз: ${room.curtain ? "да" : "нет"}, трубы: ${room.pipe ? "да" : "нет"}`;
      })
      .join("\n");

    const modal = document.querySelector("#quoteModal");
    modal.querySelector('[name="area"]').value = area.toFixed(1);
    modal.querySelector('[name="comment"]').value = "Параметры из калькулятора:\n" + comments;
    modal.classList.add("open");
    document.body.classList.add("lock");
  });

  const track = document.querySelector("#worksTrack");

  document.querySelector("#worksPrev")?.addEventListener("click", () => {
    track.scrollBy({ left: -track.clientWidth * 0.8, behavior: "smooth" });
  });

  document.querySelector("#worksNext")?.addEventListener("click", () => {
    track.scrollBy({ left: track.clientWidth * 0.8, behavior: "smooth" });
  });
});