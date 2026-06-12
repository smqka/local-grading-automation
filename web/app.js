const healthStatus = document.querySelector("#healthStatus");

async function checkHealth() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const health = await response.json();

    if (!response.ok || !health.ok) {
      throw new Error("Service health check failed");
    }

    healthStatus.textContent = health.hasOpenAiKey ? "服务正常" : "服务正常，未配置 AI key";
    healthStatus.dataset.state = health.hasOpenAiKey ? "ready" : "warning";
  } catch (error) {
    healthStatus.textContent = "服务异常";
    healthStatus.dataset.state = "error";
  }
}

checkHealth();
