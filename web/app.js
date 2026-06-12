const healthStatus = document.querySelector("#healthStatus");
const supportStatus = document.querySelector("#supportStatus");
const captureStatus = document.querySelector("#captureStatus");
const captureSize = document.querySelector("#captureSize");
const captureHint = document.querySelector("#captureHint");
const startCaptureButton = document.querySelector("#startCaptureButton");
const stopCaptureButton = document.querySelector("#stopCaptureButton");
const capturePreview = document.querySelector("#capturePreview");
const previewPlaceholder = document.querySelector("#previewPlaceholder");

let captureStream = null;

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

function detectSupport() {
  const supported = Boolean(navigator.mediaDevices?.getDisplayMedia);
  supportStatus.textContent = supported ? "支持" : "不支持";
  supportStatus.dataset.state = supported ? "ready" : "error";
  startCaptureButton.disabled = !supported;

  if (!supported) {
    captureHint.textContent = "当前浏览器不支持窗口捕获，请使用新版 Chrome 或 Edge。";
  }
}

function setCaptureState(state, message) {
  captureStatus.textContent = message;
  captureStatus.dataset.state = state;
}

function updateCaptureSize() {
  if (!capturePreview.videoWidth || !capturePreview.videoHeight) {
    captureSize.textContent = "-";
    return;
  }

  captureSize.textContent = `${capturePreview.videoWidth} x ${capturePreview.videoHeight}`;
}

function stopCapture() {
  if (captureStream) {
    for (const track of captureStream.getTracks()) {
      track.stop();
    }
  }

  captureStream = null;
  capturePreview.srcObject = null;
  previewPlaceholder.hidden = false;
  startCaptureButton.disabled = !navigator.mediaDevices?.getDisplayMedia;
  stopCaptureButton.disabled = true;
  captureSize.textContent = "-";
  setCaptureState("idle", "未开始");
  captureHint.textContent = "浏览器会要求你手动选择要共享的窗口，工具不能静默读取屏幕。";
}

async function startCapture() {
  if (!navigator.mediaDevices?.getDisplayMedia) {
    detectSupport();
    return;
  }

  try {
    setCaptureState("pending", "等待授权");
    captureHint.textContent = "请在浏览器弹窗中选择电脑微信或爱探究窗口。";
    startCaptureButton.disabled = true;

    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        frameRate: { ideal: 15, max: 30 }
      },
      audio: false
    });

    stopCapture();
    captureStream = stream;
    capturePreview.srcObject = stream;
    previewPlaceholder.hidden = true;
    stopCaptureButton.disabled = false;
    setCaptureState("ready", "捕获中");
    captureHint.textContent = "已开始预览。请确认画面只包含需要批阅的窗口，避免出现学生身份信息之外的无关内容。";

    const [videoTrack] = stream.getVideoTracks();
    videoTrack?.addEventListener("ended", stopCapture);

    await capturePreview.play();
    updateCaptureSize();
  } catch (error) {
    const userCanceled = error.name === "NotAllowedError" || error.name === "AbortError";
    setCaptureState(userCanceled ? "idle" : "error", userCanceled ? "未开始" : "捕获失败");
    captureHint.textContent = userCanceled
      ? "你取消了窗口选择，需要时可以重新点击“开始捕获”。"
      : "窗口捕获失败，请确认浏览器权限和页面访问方式。";
    startCaptureButton.disabled = false;
    stopCaptureButton.disabled = true;
  }
}

startCaptureButton.addEventListener("click", startCapture);
stopCaptureButton.addEventListener("click", stopCapture);
capturePreview.addEventListener("loadedmetadata", updateCaptureSize);
capturePreview.addEventListener("resize", updateCaptureSize);
window.addEventListener("beforeunload", stopCapture);

checkHealth();
detectSupport();
