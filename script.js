const menuGrid = document.querySelector("#menuGrid");
const filters = document.querySelector("#filters");
const status = document.querySelector("#status");
const itemCount = document.querySelector("#itemCount");

function parseCSV(text) {
    const rows = [];
    let row = [];
    let value = "";
    let inQuotes = false;

    for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"' && inQuotes && next === '"') {
        value += '"';
        i++;
    } else if (char === '"') {
        inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
        row.push(value.trim());
        value = "";
    } else if ((char === "\n" || char === "\r") && !inQuotes) {
        if (char === "\r" && next === "\n") i++;
        row.push(value.trim());
        if (row.some(cell => cell !== "")) rows.push(row);
        row = [];
        value = "";
    } else {
        value += char;
    }
    }

    if (value.length || row.length) {
    row.push(value.trim());
    if (row.some(cell => cell !== "")) rows.push(row);
    }

    if (rows.length < 2) return [];

    const headers = rows[0].map(header =>
    header.replace(/^\uFEFF/, "").trim().toLowerCase()
    );

    return rows.slice(1).map(columns => {
    const item = {};
    headers.forEach((header, index) => {
        item[header] = columns[index] || "";
    });
    return item;
    });
}

function escapeHTML(value = "") {
    return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
    })[char]);
}

function renderMenu(items, selectedCategory = "همه") {
    const visibleItems = selectedCategory === "همه"
    ? items
    : items.filter(item => item.category === selectedCategory);

    itemCount.textContent = `${visibleItems.length} انتخاب`;
    menuGrid.innerHTML = visibleItems.map((item, index) => `
    <article class="food-card">
        <div class="food-photo">
        <img
            src="${escapeHTML(item.image)}"
            alt="${escapeHTML(item.name)}"
            loading="lazy"
        />
        <span class="photo-index">${String(index + 1).padStart(2, "0")}</span>
        </div>
        <div class="food-info">
        <div class="food-title-row">
            <h3>${escapeHTML(item.name)}</h3>
            <span class="food-price">${escapeHTML(item.price)} تومان</span>
        </div>
        <p class="food-description">${escapeHTML(item.description)}</p>
        </div>
    </article>
    `).join("");

    status.hidden = visibleItems.length > 0;
    if (visibleItems.length === 0) status.textContent = "در این دسته هنوز موردی ثبت نشده است.";
}

function renderFilters(items) {
    const categories = ["همه", ...new Set(items.map(item => item.category).filter(Boolean))];

    filters.innerHTML = categories.map((category, index) => `
    <button
        class="filter-btn ${index === 0 ? "active" : ""}"
        type="button"
        aria-pressed="${index === 0}"
    >${escapeHTML(category)}</button>
    `).join("");

    filters.addEventListener("click", event => {
    const button = event.target.closest(".filter-btn");
    if (!button) return;

    filters.querySelectorAll(".filter-btn").forEach(item => {
        item.classList.toggle("active", item === button);
        item.setAttribute("aria-pressed", item === button ? "true" : "false");
    });

    renderMenu(items, button.textContent.trim());
    });
}

async function loadMenu() {
    try {
    const response = await fetch("./menu.csv", { cache: "no-store" });
    if (!response.ok) throw new Error("فایل منو پیدا نشد.");

    const text = await response.text();
    const items = parseCSV(text).filter(item =>
        item.name && item.category && item.price && item.image
    );

    if (!items.length) throw new Error("در فایل CSV غذای کاملی ثبت نشده است.");

    renderFilters(items);
    renderMenu(items);
    } catch (error) {
    status.hidden = false;
    status.textContent = "بارگذاری منو انجام نشد. فایل menu.csv را بررسی کنید و سایت را با وب‌سرور اجرا کنید.";
    console.error(error);
    }
}

loadMenu();
