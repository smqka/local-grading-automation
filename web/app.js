const healthStatus = document.querySelector("#healthStatus");
const supportStatus = document.querySelector("#supportStatus");
const captureStatus = document.querySelector("#captureStatus");
const captureSize = document.querySelector("#captureSize");
const captureHint = document.querySelector("#captureHint");
const selectionStatus = document.querySelector("#selectionStatus");
const selectionSize = document.querySelector("#selectionSize");
const cropStatus = document.querySelector("#cropStatus");
const startCaptureButton = document.querySelector("#startCaptureButton");
const stopCaptureButton = document.querySelector("#stopCaptureButton");
const refreshCropButton = document.querySelector("#refreshCropButton");
const clearSelectionButton = document.querySelector("#clearSelectionButton");
const capturePreview = document.querySelector("#capturePreview");
const selectionLayer = document.querySelector("#selectionLayer");
const cropSelection = document.querySelector("#cropSelection");
const previewPlaceholder = document.querySelector("#previewPlaceholder");
const cropCanvas = document.querySelector("#cropCanvas");
const cropPlaceholder = document.querySelector("#cropPlaceholder");

let captureStream = null;
let displayedVideoRect = null;
let selectionRect = null;
let dragStart = null;
let activePointerId = null;

const minimumSelectionSize = 24;

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
    updateSelectionLayer();
    return;
  }

  captureSize.textContent = `${capturePreview.videoWidth} x ${capturePreview.videoHeight}`;
  updateSelectionLayer();
}

function getDisplayedVideoRect() {
  const frameRect = capturePreview.getBoundingClientRect();

  if (!capturePreview.videoWidth || !capturePreview.videoHeight || !frameRect.width || !frameRect.height) {
    return null;
  }

  const videoRatio = capturePreview.videoWidth / capturePreview.videoHeight;
  const frameRatio = frameRect.width / frameRect.height;
  let width = frameRect.width;
  let height = frameRect.height;
  let left = 0;
  let top = 0;

  if (frameRatio > videoRatio) {
    width = height * videoRatio;
    left = (frameRect.width - width) / 2;
  } else {
    height = width / videoRatio;
    top = (frameRect.height - height) / 2;
  }

  return {
    left,
    top,
    width,
    height
  };
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function setSelectionControls(enabled) {
  refreshCropButton.disabled = !enabled;
  clearSelectionButton.disabled = !enabled;
}

function updateSelectionMetrics() {
  if (!selectionRect) {
    selectionStatus.textContent = "未框选";
    selectionStatus.dataset.state = "idle";
    selectionSize.textContent = "-";
    cropSelection.hidden = true;
    setSelectionControls(false);
    return;
  }

  const width = Math.round(selectionRect.width * capturePreview.videoWidth);
  const height = Math.round(selectionRect.height * capturePreview.videoHeight);
  selectionStatus.textContent = "已框选";
  selectionStatus.dataset.state = "ready";
  selectionSize.textContent = `${width} x ${height}`;
  setSelectionControls(true);
}

function drawSelectionBox() {
  if (!selectionRect || !displayedVideoRect) {
    cropSelection.hidden = true;
    return;
  }

  cropSelection.hidden = false;
  cropSelection.style.left = `${selectionRect.x * displayedVideoRect.width}px`;
  cropSelection.style.top = `${selectionRect.y * displayedVideoRect.height}px`;
  cropSelection.style.width = `${selectionRect.width * displayedVideoRect.width}px`;
  cropSelection.style.height = `${selectionRect.height * displayedVideoRect.height}px`;
}

function updateSelectionLayer() {
  displayedVideoRect = getDisplayedVideoRect();

  if (!captureStream || !displayedVideoRect) {
    selectionLayer.hidden = true;
    return;
  }

  selectionLayer.hidden = false;
  selectionLayer.style.left = `${displayedVideoRect.left}px`;
  selectionLayer.style.top = `${displayedVideoRect.top}px`;
  selectionLayer.style.width = `${displayedVideoRect.width}px`;
  selectionLayer.style.height = `${displayedVideoRect.height}px`;
  drawSelectionBox();
}

function resetCropPreview() {
  cropCanvas.hidden = true;
  cropPlaceholder.hidden = false;
  cropStatus.textContent = "未生成";
  cropStatus.dataset.state = "idle";
}

function clearSelection() {
  selectionRect = null;
  updateSelectionMetrics();
  resetCropPreview();
  captureHint.textContent = captureStream
    ? "请在预览画面上拖拽框选学生答案区域，再确认裁剪预览。"
    : "浏览器会要求你手动选择要共享的窗口，工具不能静默读取屏幕。";
}

function getLayerPoint(event) {
  const layerRect = selectionLayer.getBoundingClientRect();

  return {
    x: clamp(event.clientX - layerRect.left, 0, layerRect.width),
    y: clamp(event.clientY - layerRect.top, 0, layerRect.height),
    layerWidth: layerRect.width,
    layerHeight: layerRect.height
  };
}

function normalizeSelection(startPoint, endPoint) {
  const left = Math.min(startPoint.x, endPoint.x);
  const top = Math.min(startPoint.y, endPoint.y);
  const width = Math.abs(endPoint.x - startPoint.x);
  const height = Math.abs(endPoint.y - startPoint.y);

  return {
    x: left / endPoint.layerWidth,
    y: top / endPoint.layerHeight,
    width: width / endPoint.layerWidth,
    height: height / endPoint.layerHeight
  };
}

function cropCurrentFrame() {
  if (!selectionRect || !capturePreview.videoWidth || !capturePreview.videoHeight) {
    resetCropPreview();
    return;
  }

  const sourceX = Math.round(selectionRect.x * capturePreview.videoWidth);
  const sourceY = Math.round(selectionRect.y * capturePreview.videoHeight);
  const sourceWidth = Math.round(selectionRect.width * capturePreview.videoWidth);
  const sourceHeight = Math.round(selectionRect.height * capturePreview.videoHeight);

  if (sourceWidth < minimumSelectionSize || sourceHeight < minimumSelectionSize) {
    cropStatus.textContent = "选区过小";
    cropStatus.dataset.state = "error";
    return;
  }

  cropCanvas.width = sourceWidth;
  cropCanvas.height = sourceHeight;
  const context = cropCanvas.getContext("2d");
  context.drawImage(
    capturePreview,
    sourceX,
    sourceY,
    sourceWidth,
    sourceHeight,
    0,
    0,
    sourceWidth,
    sourceHeight
  );

  cropCanvas.hidden = false;
  cropPlaceholder.hidden = true;
  cropStatus.textContent = "已生成";
  cropStatus.dataset.state = "ready";
  captureHint.textContent = "已生成裁剪预览。请确认图片只包含学生答案区域，后续评分接口会使用这张图。";
}

function beginSelection(event) {
  if (!captureStream || !displayedVideoRect) {
    return;
  }

  activePointerId = event.pointerId;
  dragStart = getLayerPoint(event);
  selectionLayer.setPointerCapture(activePointerId);
  selectionRect = {
    x: dragStart.x / dragStart.layerWidth,
    y: dragStart.y / dragStart.layerHeight,
    width: 0,
    height: 0
  };
  resetCropPreview();
  drawSelectionBox();
  event.preventDefault();
}

function updateSelection(event) {
  if (!dragStart || activePointerId !== event.pointerId) {
    return;
  }

  const currentPoint = getLayerPoint(event);
  selectionRect = normalizeSelection(dragStart, currentPoint);
  drawSelectionBox();
  event.preventDefault();
}

function finishSelection(event) {
  if (!dragStart || activePointerId !== event.pointerId) {
    return;
  }

  const currentPoint = getLayerPoint(event);
  const layerWidth = currentPoint.layerWidth;
  const layerHeight = currentPoint.layerHeight;
  selectionRect = normalizeSelection(dragStart, currentPoint);
  dragStart = null;
  activePointerId = null;

  if (selectionLayer.hasPointerCapture(event.pointerId)) {
    selectionLayer.releasePointerCapture(event.pointerId);
  }

  const selectionWidth = selectionRect.width * layerWidth;
  const selectionHeight = selectionRect.height * layerHeight;

  if (selectionWidth < minimumSelectionSize || selectionHeight < minimumSelectionSize) {
    selectionRect = null;
    updateSelectionMetrics();
    resetCropPreview();
    captureHint.textContent = "选区太小，请重新拖拽框选完整的学生答案区域。";
    return;
  }

  updateSelectionMetrics();
  drawSelectionBox();
  cropCurrentFrame();
  event.preventDefault();
}

function stopCapture() {
  if (captureStream) {
    for (const track of captureStream.getTracks()) {
      track.stop();
    }
  }

  captureStream = null;
  capturePreview.srcObject = null;
  selectionLayer.hidden = true;
  previewPlaceholder.hidden = false;
  startCaptureButton.disabled = !navigator.mediaDevices?.getDisplayMedia;
  stopCaptureButton.disabled = true;
  captureSize.textContent = "-";
  clearSelection();
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
    startCaptureButton.disabled = true;
    stopCaptureButton.disabled = false;
    setCaptureState("ready", "捕获中");
    captureHint.textContent = "已开始预览。请在画面上拖拽框选学生答案区域。";

    const [videoTrack] = stream.getVideoTracks();
    videoTrack?.addEventListener("ended", stopCapture);

    await capturePreview.play();
    updateCaptureSize();
    updateSelectionLayer();
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
refreshCropButton.addEventListener("click", cropCurrentFrame);
clearSelectionButton.addEventListener("click", clearSelection);
capturePreview.addEventListener("loadedmetadata", updateCaptureSize);
capturePreview.addEventListener("resize", updateCaptureSize);
selectionLayer.addEventListener("pointerdown", beginSelection);
selectionLayer.addEventListener("pointermove", updateSelection);
selectionLayer.addEventListener("pointerup", finishSelection);
selectionLayer.addEventListener("pointercancel", finishSelection);
window.addEventListener("resize", updateSelectionLayer);
window.addEventListener("beforeunload", stopCapture);

checkHealth();
detectSupport();
resetCropPreview();
