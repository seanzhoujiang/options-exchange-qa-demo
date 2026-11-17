(() => {
  const API_BASE = "/api";
  const TOKEN_KEY = "access_token";

  const readJson = async (response) => {
    let payload;
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) {
      const message = payload.message ?? `请求失败（${response.status}）`;
      throw new Error(message);
    }
    return payload;
  };

  const request = async (path, options = {}) => {
    const headers = new Headers(options.headers ?? {});
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (token && options.auth !== false) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    return readJson(response);
  };

  const setMessage = (element, text) => {
    element.textContent = text;
  };

  const initLogin = () => {
    const form = document.querySelector("#login-form");
    const codeOutput = document.querySelector("#captcha-code");
    const answerInput = document.querySelector("#captcha-answer");
    const message = document.querySelector("#login-message");
    const refreshButton = document.querySelector("#refresh-captcha");
    const submitButton = document.querySelector("#login-submit");
    let captchaId = null;

    const loadCaptcha = async () => {
      refreshButton.disabled = true;
      setMessage(message, "");
      codeOutput.textContent = "…";
      try {
        const payload = await request("/auth/captcha", { method: "POST", auth: false });
        captchaId = payload.captcha_id;
        const code = payload.captcha_code;
        codeOutput.textContent = code;
        answerInput.value = "";
      } catch (error) {
        captchaId = null;
        codeOutput.textContent = "不可用";
        setMessage(message, error.message);
      } finally {
        refreshButton.disabled = false;
      }
    };

    refreshButton.addEventListener("click", loadCaptcha);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      setMessage(message, "");
      if (!form.reportValidity()) return;
      if (!captchaId) {
        setMessage(message, "请先获取验证码。");
        return;
      }
      const formData = new FormData(form);
      submitButton.disabled = true;
      submitButton.querySelector("span:first-child").textContent = "正在登录…";
      try {
        const payload = await request("/auth/login", {
          method: "POST",
          auth: false,
          body: JSON.stringify({
            username: String(formData.get("username")).trim(),
            password: String(formData.get("password")),
            captcha_id: captchaId,
            captcha_code: String(formData.get("captcha")).trim(),
          }),
        });
        sessionStorage.setItem(TOKEN_KEY, payload.token);
        window.location.assign("/trade");
      } catch (error) {
        setMessage(message, error.message);
        captchaId = null;
      } finally {
        submitButton.disabled = false;
        submitButton.querySelector("span:first-child").textContent = "登录并进入";
      }
    });
    loadCaptcha();
  };

  const initTrade = () => {
    const orderForm = document.querySelector("#order-form");
    const tradeMessage = document.querySelector("#trade-message");
    const orderMessage = document.querySelector("#order-message");
    const instrumentSelect = document.querySelector("#instrument-select");
    const submitButton = document.querySelector("#submit-order");
    const refreshButton = document.querySelector("#refresh-data");

    if (!sessionStorage.getItem(TOKEN_KEY)) {
      window.location.replace("/login");
      return;
    }

    const renderInstruments = (instruments) => {
      instrumentSelect.replaceChildren();
      const placeholderOption = document.createElement("option");
      placeholderOption.value = "";
      placeholderOption.textContent = "选择期权合约";
      instrumentSelect.append(placeholderOption);
      for (const instrument of instruments) {
        const option = document.createElement("option");
        option.value = instrument.name;
        option.textContent = instrument.name;
        instrumentSelect.append(option);
      }
      document.querySelector("#instrument-count").textContent = String(instruments.length);

      const body = document.querySelector("#instrument-rows");
      body.replaceChildren();
      for (const instrument of instruments) {
        const row = document.createElement("tr");
        const symbolCell = document.createElement("td");
        symbolCell.className = "contract-name";
        symbolCell.textContent = String(instrument.name);
        const typeCell = document.createElement("td");
        const typeTag = document.createElement("span");
        const type = instrument.option_type;
        typeTag.className = `type-tag${type === "put" ? " put" : ""}`;
        typeTag.textContent = type === "put" ? "看跌 PUT" : "看涨 CALL";
        typeCell.append(typeTag);
        const strikeCell = document.createElement("td");
        strikeCell.textContent = String(instrument.strike);
        const expiryCell = document.createElement("td");
        expiryCell.textContent = String(instrument.expiry);
        row.append(symbolCell, typeCell, strikeCell, expiryCell);
        body.append(row);
      }
    };

    const renderAccount = (account) => {
      document.querySelector("#account-balance").textContent = String(account.balance);
      document.querySelector("#account-available").textContent = String(account.available);
      document.querySelector("#account-frozen").textContent = String(account.frozen);
      document.querySelector("#account-status").textContent = String(account.status);
    };

    const renderOrders = (orders) => {
      const body = document.querySelector("#order-rows");
      body.replaceChildren();
      document.querySelector("#orders-count").textContent = String(orders.length);
      if (!orders.length) {
        body.innerHTML = '<tr><td class="empty-cell" colspan="6">暂无未完成委托</td></tr>';
        return;
      }
      for (const order of orders) {
        const row = document.createElement("tr");
        row.dataset.testid = "open-order-row";
        const cells = [
          ["contract-name", String(order.instrument)],
          [order.side === "sell" ? "side-sell" : "side-buy", order.side === "sell" ? "卖出" : "买入"],
          ["", String(order.price)],
          ["", String(order.quantity)],
          ["", String(order.status)],
        ];
        for (const [className, value] of cells) {
          const cell = document.createElement("td");
          if (className) cell.className = className;
          cell.textContent = value;
          row.append(cell);
        }
        const actionCell = document.createElement("td");
        const cancelButton = document.createElement("button");
        cancelButton.type = "button";
        cancelButton.className = "cancel-button";
        cancelButton.textContent = "撤销";
        cancelButton.dataset.testid = "cancel-order-button";
        cancelButton.addEventListener("click", () => cancelOrder(order.order_id, cancelButton));
        actionCell.append(cancelButton);
        row.append(actionCell);
        body.append(row);
      }
    };

    const renderPositions = (positions) => {
      const body = document.querySelector("#position-rows");
      body.replaceChildren();
      document.querySelector("#positions-count").textContent = String(positions.length);
      if (!positions.length) {
        body.innerHTML = '<tr><td class="empty-cell" colspan="5">暂无持仓</td></tr>';
        return;
      }
      for (const position of positions) {
        const row = document.createElement("tr");
        row.dataset.testid = "position-row";
        const values = [
          ["contract-name", position.instrument],
          ["", position.quantity, "position-quantity"],
          ["", position.average_price],
          ["", position.mark_price],
          ["", position.unrealized_pnl],
        ];
        for (const [className, value, testId] of values) {
          const cell = document.createElement("td");
          if (testId) cell.dataset.testid = testId;
          if (className) cell.className = className;
          cell.textContent = String(value);
          row.append(cell);
        }
        body.append(row);
      }
    };

    const cancelOrder = async (orderId, button) => {
      button.disabled = true;
      setMessage(tradeMessage, "正在撤销委托…");
      try {
        await request(`/orders/${encodeURIComponent(String(orderId))}`, { method: "DELETE" });
        await loadTradeData();
        setMessage(tradeMessage, "委托已撤销。");
      } catch (error) {
        button.disabled = false;
        setMessage(tradeMessage, error.message);
      }
    };

    const loadOne = async (path, render, messageElement, label) => {
      try {
        const payload = await request(path);
        render(payload);
        setMessage(messageElement, "");
        return null;
      } catch (error) {
        setMessage(messageElement, `${label}加载失败：${error.message}`);
        return error;
      }
    };

    async function loadTradeData() {
      refreshButton.disabled = true;
      const tasks = [
        loadOne("/account", renderAccount, tradeMessage, "账户"),
        loadOne("/instruments", renderInstruments, document.querySelector("#instruments-message"), "合约"),
        loadOne("/orders?status=open", renderOrders, document.querySelector("#orders-message"), "委托"),
        loadOne("/positions", renderPositions, document.querySelector("#positions-message"), "持仓"),
      ];
      await Promise.all(tasks);
      refreshButton.disabled = false;
    }

    orderForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      setMessage(orderMessage, "");
      if (!orderForm.reportValidity()) return;
      const formData = new FormData(orderForm);
      const price = String(formData.get("price")).trim();
      const quantity = String(formData.get("quantity")).trim();
      if (!price || !quantity || !Number.isFinite(Number(price)) || !Number.isFinite(Number(quantity)) || Number(price) <= 0 || Number(quantity) <= 0) {
        setMessage(orderMessage, "请输入大于零的有效价格和数量。");
        return;
      }
      submitButton.disabled = true;
      submitButton.querySelector("span:first-child").textContent = "正在提交…";
      try {
        await request("/orders", {
          method: "POST",
          body: JSON.stringify({
            instrument: String(formData.get("instrument")),
            side: String(formData.get("side")),
            price,
            quantity,
          }),
        });
        orderForm.reset();
        setMessage(orderMessage, "委托已提交。");
        await loadTradeData();
      } catch (error) {
        setMessage(orderMessage, error.message);
      } finally {
        submitButton.disabled = false;
        submitButton.querySelector("span:first-child").textContent = "提交委托";
      }
    });

    refreshButton.addEventListener("click", loadTradeData);
    document.querySelector("#logout-button").addEventListener("click", async () => {
      try {
        await request("/auth/logout", { method: "POST" });
      } catch (error) {
        setMessage(tradeMessage, error.message);
        return;
      }
      sessionStorage.removeItem(TOKEN_KEY);
      window.location.assign("/login");
    });
    loadTradeData();
  };

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page === "login") initLogin();
    if (document.body.dataset.page === "trade") initTrade();
  });
})();
