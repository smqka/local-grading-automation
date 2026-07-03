const CONFIG_KEY = "exam-grading-assistant:question-config:v1";
const CROP_KEY = "exam-grading-assistant:crop-box:v1";
const CLICK_CONFIG_KEY = "exam-grading-assistant:click-config:v1";
const HISTORY_KEY = "exam-grading-assistant:history:v1";
const MAX_HISTORY_ITEMS = 8;
const CROP_OUTPUT_SCALE = 2;
const CROP_ENHANCE_FILTER = "brightness(1.03) contrast(1.08)";
const DEFAULT_CONFIDENCE_THRESHOLD_PERCENT = 80;
const COORDINATE_CAPTURE_DELAY_MS = 2500;
const DEFAULT_PAGE_REFRESH_DELAY_MS = 1000;

const elements = {
  healthStatus: document.querySelector("#healthStatus"),
  apiTarget: document.querySelector("#apiTarget"),
  captureStatus: document.querySelector("#captureStatus"),
  startCaptureBtn: document.querySelector("#startCaptureBtn"),
  snapshotBtn: document.querySelector("#snapshotBtn"),
  stopCaptureBtn: document.querySelector("#stopCaptureBtn"),
  previewFrame: document.querySelector("#previewFrame"),
  captureVideo: document.querySelector("#captureVideo"),
  selectionOverlay: document.querySelector("#selectionOverlay"),
  cropBox: document.querySelector("#cropBox"),
  previewEmpty: document.querySelector("#previewEmpty"),
  cropCanvas: document.querySelector("#cropCanvas"),
  cropEmpty: document.querySelector("#cropEmpty"),
  cropSize: document.querySelector("#cropSize"),
  gradingForm: document.querySelector("#gradingForm"),
  submitGradeBtn: document.querySelector("#submitGradeBtn"),
  clearConfigBtn: document.querySelector("#clearConfigBtn"),
  clearHistoryBtn: document.querySelector("#clearHistoryBtn"),
  saveStatus: document.querySelector("#saveStatus"),
  resultStatus: document.querySelector("#resultStatus"),
  reviewBadge: document.querySelector("#reviewBadge"),
  suggestedScore: document.querySelector("#suggestedScore"),
  confidence: document.querySelector("#confidence"),
  modelName: document.querySelector("#modelName"),
  uncertainList: document.querySelector("#uncertainList"),
  reviewReason: document.querySelector("#reviewReason"),
  historyList: document.querySelector("#historyList"),
  autoClickEnabled: document.querySelector("#autoClickEnabled"),
  confidenceThreshold: document.querySelector("#confidenceThreshold"),
  lowConfidenceAction: document.querySelector("#lowConfidenceAction"),
  pageRefreshDelayMs: document.querySelector("#pageRefreshDelayMs"),
  clickStatus: document.querySelector("#clickStatus"),
  mousePosition: document.querySelector("#mousePosition"),
  refreshMouseBtn: document.querySelector("#refreshMouseBtn"),
  recordNextClickBtn: document.querySelector("#recordNextClickBtn"),
  testNextClickBtn: document.querySelector("#testNextClickBtn"),
  nextClickPoint: document.querySelector("#nextClickPoint"),
  startAutoFlowBtn: document.querySelector("#startAutoFlowBtn"),
  pauseAutoFlowBtn: document.querySelector("#pauseAutoFlowBtn"),
  continueAutoFlowBtn: document.querySelector("#continueAutoFlowBtn"),
  refreshScoreClickGridBtn: document.querySelector("#refreshScoreClickGridBtn"),
  scoreClickGrid: document.querySelector("#scoreClickGrid")
};

const fields = {
  questionId: document.querySelector("#questionId"),
  maxScore: document.querySelector("#maxScore"),
  scorePrecision: document.querySelector("#scorePrecision"),
  ruleVersion: document.querySelector("#ruleVersion"),
  standardAnswer: document.querySelector("#standardAnswer"),
  gradingRules: document.querySelector("#gradingRules"),
  deductionRules: document.querySelector("#deductionRules"),
  allowEquivalentAnswers: document.querySelector("#allowEquivalentAnswers"),
  scoreBySteps: document.querySelector("#scoreBySteps")
};

let mediaStream = null;
let cropRect = null;
let croppedImage = "";
let dragStart = null;
let isSubmitting = false;
let isRecordingPoint = false;
let autoFlowState = "idle";
let autoRunId = 0;
let clickConfig = {
  enabled: false,
  confidence_threshold_percent: DEFAULT_CONFIDENCE_THRESHOLD_PERCENT,
  low_confidence_action: "review",
  page_delay_ms: DEFAULT_PAGE_REFRESH_DELAY_MS,
  next: null,
  scores: {}
};

function updatePreviewAspectRatio() {
  if (!elements.captureVideo.videoWidth || !elements.captureVideo.videoHeight) {
    elements.previewFrame.style.removeProperty("--capture-aspect-ratio");
    return;
  }

  elements.previewFrame.style.setProperty(
    "--capture-aspect-ratio",
    `${elements.captureVideo.videoWidth} / ${elements.captureVideo.videoHeight}`
  );
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const health = await response.json();

    if (!response.ok || !health.ok) {
      throw new Error("Service health check failed");
    }

    const gradingApiReady = Boolean(health.gradingApi?.ok);
    const gradingApiHasKey = health.gradingApi?.hasOpenAiKey !== false;
    if (!health.hasOpenAiKey || !gradingApiHasKey) {
      elements.healthStatus.textContent = "未配置 AI key";
      elements.healthStatus.dataset.state = "warning";
    } else if (!gradingApiReady) {
      elements.healthStatus.textContent = "评分 API 未启动";
      elements.healthStatus.dataset.state = "warning";
    } else {
      elements.healthStatus.textContent = "服务正常";
      elements.healthStatus.dataset.state = "ready";
    }
    elements.apiTarget.textContent = health.gradingApiBaseUrl ? `评分 API：${health.gradingApiBaseUrl}` : "";
  } catch {
    elements.healthStatus.textContent = "网页服务异常";
    elements.healthStatus.dataset.state = "error";
    elements.apiTarget.textContent = "";
  }
}

async function startCapture() {
  if (!navigator.mediaDevices?.getDisplayMedia) {
    setCaptureStatus("当前浏览器不支持屏幕捕获，请使用 Chrome 或 Edge。", "error");
    return;
  }

  clearCroppedImage();

  try {
    mediaStream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        cursor: "always",
        displaySurface: "window"
      },
      audio: false
    });
  } catch {
    setCaptureStatus("已取消捕获选择。", "warning");
    return;
  }

  elements.captureVideo.srcObject = mediaStream;
  elements.previewEmpty.classList.add("is-hidden");
  elements.startCaptureBtn.disabled = true;
  elements.snapshotBtn.disabled = false;
  elements.stopCaptureBtn.disabled = false;
  setCaptureStatus("捕获中，拖拽画面框选学生答案区域。", "ready");

  const [track] = mediaStream.getVideoTracks();
  track.addEventListener("ended", stopCapture);

  await elements.captureVideo.play();
  updatePreviewAspectRatio();
  restoreCropBox();
  refreshSubmitState();
  updateAutoFlowControls();
}

function stopCapture() {
  pauseAutoFlow("捕获已停止，自动批卷暂停。");
  if (mediaStream) {
    for (const track of mediaStream.getTracks()) {
      track.stop();
    }
  }

  mediaStream = null;
  elements.captureVideo.srcObject = null;
  elements.previewFrame.style.removeProperty("--capture-aspect-ratio");
  elements.previewEmpty.classList.remove("is-hidden");
  elements.startCaptureBtn.disabled = false;
  elements.snapshotBtn.disabled = true;
  elements.stopCaptureBtn.disabled = true;
  clearCroppedImage();
  setCaptureStatus("捕获已停止。", "warning");
  refreshSubmitState();
  updateAutoFlowControls();
}

function beginSelection(event) {
  if (!mediaStream || event.button !== 0) {
    return;
  }

  const bounds = elements.selectionOverlay.getBoundingClientRect();
  dragStart = {
    x: clamp(event.clientX - bounds.left, 0, bounds.width),
    y: clamp(event.clientY - bounds.top, 0, bounds.height),
    bounds
  };

  cropRect = { x: dragStart.x, y: dragStart.y, width: 0, height: 0 };
  renderCropBox();
  elements.selectionOverlay.setPointerCapture(event.pointerId);
}

function updateSelection(event) {
  if (!dragStart) {
    return;
  }

  const x = clamp(event.clientX - dragStart.bounds.left, 0, dragStart.bounds.width);
  const y = clamp(event.clientY - dragStart.bounds.top, 0, dragStart.bounds.height);
  const left = Math.min(dragStart.x, x);
  const top = Math.min(dragStart.y, y);

  cropRect = {
    x: left,
    y: top,
    width: Math.abs(x - dragStart.x),
    height: Math.abs(y - dragStart.y)
  };
  renderCropBox();
}

function endSelection(event) {
  if (!dragStart) {
    return;
  }

  elements.selectionOverlay.releasePointerCapture(event.pointerId);
  dragStart = null;

  if (!cropRect || cropRect.width < 12 || cropRect.height < 12) {
    cropRect = null;
    clearCroppedImage();
    elements.cropBox.classList.add("is-hidden");
    elements.cropSize.textContent = "框选区域过小";
    refreshSubmitState();
    return;
  }

  persistCropBox();
  captureCrop();
}

function renderCropBox() {
  if (!cropRect) {
    elements.cropBox.classList.add("is-hidden");
    return;
  }

  elements.cropBox.classList.remove("is-hidden");
  elements.cropBox.style.left = `${cropRect.x}px`;
  elements.cropBox.style.top = `${cropRect.y}px`;
  elements.cropBox.style.width = `${cropRect.width}px`;
  elements.cropBox.style.height = `${cropRect.height}px`;
  elements.cropSize.textContent = `${Math.round(cropRect.width)} × ${Math.round(cropRect.height)} px`;
}

function captureCrop() {
  if (!mediaStream) {
    setCaptureStatus("请先点击“开始捕获”，选择要批阅的窗口。", "warning");
    refreshSubmitState();
    return false;
  }

  if (!cropRect) {
    setCaptureStatus("请在上方预览画面按住鼠标左键拖拽，框选学生答案区域。", "warning");
    elements.cropSize.textContent = "请先拖拽框选";
    emphasizePreviewFrame();
    refreshSubmitState();
    return false;
  }

  if (!elements.captureVideo.videoWidth || !elements.captureVideo.videoHeight) {
    setCaptureStatus("捕获画面还未准备好，请稍等一秒后重试。", "warning");
    refreshSubmitState();
    return false;
  }

  const videoBounds = elements.captureVideo.getBoundingClientRect();
  if (!videoBounds.width || !videoBounds.height) {
    setCaptureStatus("捕获画面尺寸异常，请重新开始捕获。", "error");
    refreshSubmitState();
    return false;
  }

  const scaleX = elements.captureVideo.videoWidth / videoBounds.width;
  const scaleY = elements.captureVideo.videoHeight / videoBounds.height;
  const sourceX = Math.round(cropRect.x * scaleX);
  const sourceY = Math.round(cropRect.y * scaleY);
  const sourceWidth = Math.round(cropRect.width * scaleX);
  const sourceHeight = Math.round(cropRect.height * scaleY);

  if (sourceWidth <= 0 || sourceHeight <= 0) {
    setCaptureStatus("裁剪区域无效，请重新框选。", "error");
    refreshSubmitState();
    return false;
  }

  const outputWidth = sourceWidth * CROP_OUTPUT_SCALE;
  const outputHeight = sourceHeight * CROP_OUTPUT_SCALE;

  elements.cropCanvas.width = outputWidth;
  elements.cropCanvas.height = outputHeight;
  const context = elements.cropCanvas.getContext("2d", { willReadFrequently: false });
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.filter = CROP_ENHANCE_FILTER;
  context.drawImage(
    elements.captureVideo,
    sourceX,
    sourceY,
    sourceWidth,
    sourceHeight,
    0,
    0,
    outputWidth,
    outputHeight
  );

  croppedImage = elements.cropCanvas.toDataURL("image/png");
  elements.cropEmpty.classList.add("is-hidden");
  elements.cropSize.textContent = `裁剪图 ${sourceWidth} × ${sourceHeight} px，提交图 ${outputWidth} × ${outputHeight} px`;
  setCaptureStatus("裁剪图已更新。", "ready");
  refreshSubmitState();
  return true;
}

function emphasizePreviewFrame() {
  elements.previewFrame.classList.add("is-attention");
  window.clearTimeout(emphasizePreviewFrame.timer);
  emphasizePreviewFrame.timer = window.setTimeout(() => {
    elements.previewFrame.classList.remove("is-attention");
  }, 1400);
}

function restoreCropBox() {
  const saved = readStorage(CROP_KEY);
  if (!saved || !elements.previewFrame.clientWidth || !elements.previewFrame.clientHeight) {
    return;
  }

  cropRect = {
    x: saved.x * elements.previewFrame.clientWidth,
    y: saved.y * elements.previewFrame.clientHeight,
    width: saved.width * elements.previewFrame.clientWidth,
    height: saved.height * elements.previewFrame.clientHeight
  };
  renderCropBox();
}

function persistCropBox() {
  if (!cropRect) {
    return;
  }

  const bounds = elements.previewFrame.getBoundingClientRect();
  writeStorage(CROP_KEY, {
    x: cropRect.x / bounds.width,
    y: cropRect.y / bounds.height,
    width: cropRect.width / bounds.width,
    height: cropRect.height / bounds.height
  });
}

function loadConfig() {
  const saved = readStorage(CONFIG_KEY);
  if (!saved) {
    return;
  }

  fields.questionId.value = saved.question_id || "";
  fields.maxScore.value = saved.max_score || "6";
  fields.scorePrecision.value = saved.score_precision || "0.5";
  fields.ruleVersion.value = saved.rule_version || "";
  fields.standardAnswer.value = saved.standard_answer || "";
  fields.gradingRules.value = saved.grading_rules || "";
  fields.deductionRules.value = saved.deduction_rules || "";
  fields.allowEquivalentAnswers.checked = saved.allow_equivalent_answers !== false;
  fields.scoreBySteps.checked = saved.score_by_steps !== false;
}

function saveConfig() {
  writeStorage(CONFIG_KEY, collectConfig());
  elements.saveStatus.textContent = "已保存";
  window.clearTimeout(saveConfig.timer);
  saveConfig.timer = window.setTimeout(() => {
    elements.saveStatus.textContent = "本地保存";
  }, 1200);
  refreshSubmitState();
  renderScoreClickGrid();
}

function collectConfig() {
  return {
    question_id: fields.questionId.value.trim(),
    max_score: Number(fields.maxScore.value),
    standard_answer: fields.standardAnswer.value.trim(),
    grading_rules: fields.gradingRules.value.trim(),
    deduction_rules: fields.deductionRules.value.trim(),
    allow_equivalent_answers: fields.allowEquivalentAnswers.checked,
    score_by_steps: fields.scoreBySteps.checked,
    score_precision: fields.scorePrecision.value,
    rule_version: fields.ruleVersion.value.trim()
  };
}

function collectPayload(config) {
  return {
    ...config,
    question_id: config.question_id || null,
    rule_version: config.rule_version || null,
    mode: "suggest_only",
    image: croppedImage
  };
}

function loadClickConfig() {
  const saved = readStorage(CLICK_CONFIG_KEY) || {};
  clickConfig = {
    enabled: Boolean(saved.enabled),
    confidence_threshold_percent: normalizeConfidenceThresholdPercent(
      saved.confidence_threshold_percent ?? saved.confidence_threshold
    ),
    low_confidence_action: saved.low_confidence_action === "skip" ? "skip" : "review",
    page_delay_ms: normalizePageDelayMs(saved.page_delay_ms),
    next: sanitizePoint(saved.next),
    scores: sanitizeScorePoints(saved.scores)
  };

  elements.autoClickEnabled.checked = clickConfig.enabled;
  elements.confidenceThreshold.value = String(clickConfig.confidence_threshold_percent);
  elements.lowConfidenceAction.value = clickConfig.low_confidence_action;
  elements.pageRefreshDelayMs.value = formatDelaySeconds(clickConfig.page_delay_ms);
  renderClickPanel();
  updateAutoFlowControls();
}

function saveClickConfig() {
  clickConfig.enabled = elements.autoClickEnabled.checked;
  clickConfig.confidence_threshold_percent = normalizeConfidenceThresholdPercent(elements.confidenceThreshold.value);
  clickConfig.low_confidence_action = elements.lowConfidenceAction.value === "skip" ? "skip" : "review";
  clickConfig.page_delay_ms = normalizePageDelaySecondsToMs(elements.pageRefreshDelayMs.value);
  writeStorage(CLICK_CONFIG_KEY, clickConfig);
  renderClickPanel();
}

function renderClickPanel() {
  if (autoFlowState === "idle") {
    elements.clickStatus.textContent = clickConfig.enabled ? "已启用" : "未启用";
    elements.clickStatus.dataset.state = clickConfig.enabled ? "ready" : "warning";
  }
  elements.nextClickPoint.textContent = formatPoint(clickConfig.next);
  elements.testNextClickBtn.disabled = !clickConfig.next;
  renderScoreClickGrid();
  updateAutoFlowControls();
}

function renderScoreClickGrid() {
  elements.scoreClickGrid.replaceChildren();
  const values = buildScoreValues();

  if (!values.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "暂无分值";
    elements.scoreClickGrid.append(empty);
    return;
  }

  if (values.length > 240) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "分值过多";
    elements.scoreClickGrid.append(empty);
    return;
  }

  for (const value of values) {
    const key = scoreKey(value);
    const row = document.createElement("div");
    row.className = "score-click-item";

    const label = document.createElement("span");
    label.textContent = formatScore(value);

    const pointLabel = document.createElement("strong");
    pointLabel.textContent = formatPoint(clickConfig.scores[key]);

    const button = document.createElement("button");
    button.className = "button";
    button.type = "button";
    button.textContent = "记录";
    button.addEventListener("click", () => recordScoreClickPoint(value));

    row.append(label, pointLabel, button);
    elements.scoreClickGrid.append(row);
  }
}

function buildScoreValues() {
  const maxScore = Number(fields.maxScore.value);
  if (!Number.isFinite(maxScore) || maxScore < 0) {
    return [];
  }

  const step = getScoreStep();
  const values = [];
  const count = Math.floor(maxScore / step + 1e-8);
  for (let index = 0; index <= count; index += 1) {
    values.push(roundScore(index * step));
  }

  const roundedMax = roundScore(maxScore);
  if (!values.length || scoreKey(values[values.length - 1]) !== scoreKey(roundedMax)) {
    values.push(roundedMax);
  }
  return values;
}

function getScoreStep() {
  if (fields.scorePrecision.value === "integer") {
    return 1;
  }

  const step = Number(fields.scorePrecision.value);
  return Number.isFinite(step) && step > 0 ? step : 0.5;
}

async function refreshMousePosition() {
  try {
    const point = await fetchMousePosition();
    elements.mousePosition.textContent = formatPoint(point);
    setClickStatus("已读取坐标", "ready");
    return point;
  } catch (error) {
    setClickStatus(error.message || "读取坐标失败", "error");
    return null;
  }
}

async function fetchMousePosition() {
  const response = await fetch("/api/mouse-position", { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || payload.error || "读取坐标失败");
  }

  const point = sanitizePoint(payload);
  if (!point) {
    throw new Error("坐标数据无效");
  }
  return point;
}

async function recordNextClickPoint() {
  const point = await captureMouseAfterDelay("跳过");
  if (!point) {
    return;
  }

  clickConfig.next = point;
  saveClickConfig();
  setClickStatus("已记录跳过坐标", "ready");
}

async function recordScoreClickPoint(value) {
  const point = await captureMouseAfterDelay(`${formatScore(value)} 分`);
  if (!point) {
    return;
  }

  clickConfig.scores[scoreKey(value)] = point;
  saveClickConfig();
  setClickStatus(`已记录 ${formatScore(value)} 分坐标`, "ready");
}

async function captureMouseAfterDelay(label) {
  if (isRecordingPoint) {
    setClickStatus("正在记录坐标", "warning");
    return null;
  }

  isRecordingPoint = true;
  setClickStatus(`${label}：2.5 秒后读取鼠标位置`, "warning");
  try {
    await wait(COORDINATE_CAPTURE_DELAY_MS);
    return await refreshMousePosition();
  } finally {
    isRecordingPoint = false;
  }
}

async function testNextClickPoint() {
  if (!clickConfig.next) {
    setClickStatus("未记录跳过坐标", "warning");
    return;
  }

  try {
    await executeClickSequence([clickConfig.next]);
    setClickStatus("已测试跳过点击", "ready");
  } catch (error) {
    setClickStatus(error.message || "测试点击失败", "error");
  }
}

async function maybeAutoClick(result) {
  if (!clickConfig.enabled) {
    setClickStatus("自动点击未启用", "warning");
    return false;
  }

  const suggestedScore = Number(result.suggested_score);
  const score = roundScoreToPrecision(suggestedScore);
  const scorePoint = clickConfig.scores[scoreKey(score)] || clickConfig.scores[scoreKey(suggestedScore)];
  if (!scorePoint) {
    setClickStatus(`缺少 ${formatScore(score)} 分坐标`, "warning");
    return false;
  }

  try {
    await executeClickSequence([scorePoint]);
    setClickStatus("已点击分数，等待系统自动翻页", "ready");
    return true;
  } catch (error) {
    setClickStatus(error.message || "自动点击失败", "error");
    return false;
  }
}

async function clickNextPageOnly() {
  if (!clickConfig.next) {
    throw new Error("缺少跳过坐标");
  }
  await executeClickSequence([clickConfig.next]);
}

function decideAutoAction(result) {
  const confidence = normalizeConfidenceRatio(result.confidence);
  const suggestedScore = Number(result.suggested_score);
  const threshold = getConfidenceThreshold();
  const canAutoScore = confidence >= threshold && !result.needs_review && Number.isFinite(suggestedScore);

  if (canAutoScore) {
    return "score";
  }
  return clickConfig.low_confidence_action === "skip" ? "skip" : "review";
}

function validateAutoFlowStart() {
  if (!clickConfig.enabled) {
    return "请先启用自动点击";
  }
  if (!mediaStream) {
    return "请先开始捕获阅卷窗口";
  }
  if (!cropRect) {
    return "请先框选答案区域";
  }
  if (clickConfig.low_confidence_action === "skip" && !clickConfig.next) {
    return "低于阈值设为自动跳过时，请先记录跳过坐标";
  }

  const validationMessage = validateConfig(collectConfig());
  if (validationMessage) {
    return validationMessage;
  }
  return "";
}

async function startAutoFlow() {
  const validationMessage = validateAutoFlowStart();
  if (validationMessage) {
    setClickStatus(validationMessage, "warning");
    return;
  }

  autoFlowState = "running";
  autoRunId += 1;
  const runId = autoRunId;
  setClickStatus("自动批卷中", "ready");
  updateAutoFlowControls();
  await runAutoLoop(runId);
}

function pauseAutoFlow(message = "已暂停") {
  if (autoFlowState !== "running") {
    return;
  }

  autoFlowState = "paused";
  autoRunId += 1;
  setClickStatus(message, "warning");
  updateAutoFlowControls();
  refreshSubmitState();
}

async function continueAutoFlow() {
  const validationMessage = validateAutoFlowStart();
  if (validationMessage) {
    setClickStatus(validationMessage, "warning");
    return;
  }

  autoFlowState = "running";
  autoRunId += 1;
  const runId = autoRunId;
  setClickStatus("继续批卷中", "ready");
  updateAutoFlowControls();
  await runAutoLoop(runId, getPageRefreshDelayMs());
}

async function runAutoLoop(runId, initialDelayMs = 0) {
  let delayBeforeCapture = normalizePageDelayMs(initialDelayMs);

  while (isAutoRunActive(runId)) {
    if (delayBeforeCapture > 0) {
      setClickStatus(`${delayBeforeCapture}ms 后刷新截图`, "ready");
      await wait(delayBeforeCapture);
      if (!isAutoRunActive(runId)) {
        return;
      }
    }

    if (!captureCrop()) {
      pauseAutoFlow("刷新截图失败，已暂停");
      return;
    }

    let result;
    try {
      result = await requestGradeResult("自动批卷中：等待模型返回。");
    } catch (error) {
      if (!isAutoRunActive(runId)) {
        return;
      }
      renderError(error.message || "评分请求失败");
      pauseAutoFlow("评分失败，已暂停");
      return;
    }

    if (!isAutoRunActive(runId)) {
      return;
    }

    const action = decideAutoAction(result);
    const autoAccepted = action === "score";
    renderResult(result, { autoAccepted, action });

    if (action === "score") {
      if (!(await maybeAutoClick(result))) {
        pauseAutoFlow("自动点击失败，已暂停");
        return;
      }
      addHistoryItem(result, { autoAccepted: true });
      delayBeforeCapture = getPageRefreshDelayMs();
      continue;
    }

    if (action === "skip") {
      try {
        await clickNextPageOnly();
      } catch (error) {
        setClickStatus(error.message || "自动跳过失败", "error");
        pauseAutoFlow("自动跳过失败，已暂停");
        return;
      }
      addHistoryItem(result, { skipped: true });
      setResultStatus(autoHoldMessage(result, "已自动跳过。"), "warning");
      setClickStatus("已跳过，等待页面切换", "ready");
      delayBeforeCapture = getPageRefreshDelayMs();
      continue;
    }

    addHistoryItem(result, { needsManual: true });
    setResultStatus(autoHoldMessage(result, "等待人工审核。"), "warning");
    pauseAutoFlow("等待人工审核，处理后点继续");
    return;
  }
}

function isAutoRunActive(runId) {
  return autoFlowState === "running" && autoRunId === runId;
}

function updateAutoFlowControls() {
  const isRunning = autoFlowState === "running";
  const isPaused = autoFlowState === "paused";

  elements.startAutoFlowBtn.disabled = isRunning || isPaused || isSubmitting;
  elements.pauseAutoFlowBtn.disabled = !isRunning;
  elements.continueAutoFlowBtn.disabled = !isPaused || isSubmitting;
}

async function executeClickSequence(points) {
  const response = await fetch("/api/click-sequence", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      points,
      delay_ms: 0
    })
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || payload.error || "点击失败");
  }
  return payload;
}

function sanitizeScorePoints(scores) {
  const result = {};
  if (!scores || typeof scores !== "object") {
    return result;
  }

  for (const [key, value] of Object.entries(scores)) {
    const point = sanitizePoint(value);
    if (point) {
      result[scoreKey(key)] = point;
    }
  }
  return result;
}

function sanitizePoint(point) {
  if (!point || typeof point !== "object") {
    return null;
  }

  const x = Number(point.x);
  const y = Number(point.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }
  return { x: Math.round(x), y: Math.round(y) };
}

function normalizePageDelayMs(value) {
  const delay = Number(value);
  if (!Number.isFinite(delay)) {
    return DEFAULT_PAGE_REFRESH_DELAY_MS;
  }
  return Math.round(clamp(delay, 0, 5000));
}

function normalizePageDelaySecondsToMs(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) {
    return DEFAULT_PAGE_REFRESH_DELAY_MS;
  }
  return Math.round(clamp(seconds, 0, 5) * 1000);
}

function getPageRefreshDelayMs() {
  return normalizePageDelaySecondsToMs(elements.pageRefreshDelayMs.value);
}

function normalizeConfidenceThresholdPercent(value) {
  const threshold = Number(value);
  if (!Number.isFinite(threshold)) {
    return DEFAULT_CONFIDENCE_THRESHOLD_PERCENT;
  }
  if (threshold > 0 && threshold <= 1) {
    return Math.round(clamp(threshold * 100, 1, 100));
  }
  return Math.round(clamp(threshold, 1, 100));
}

function getConfidenceThreshold() {
  return normalizeConfidenceThresholdPercent(elements.confidenceThreshold.value) / 100;
}

async function requestGradeResult(statusText = "正在请求评分 API。") {
  const config = collectConfig();
  const validationMessage = validateConfig(config);
  if (validationMessage) {
    throw new Error(validationMessage);
  }
  if (!croppedImage) {
    throw new Error("请先框选答案区域并生成裁剪图。");
  }

  isSubmitting = true;
  elements.submitGradeBtn.disabled = true;
  elements.submitGradeBtn.textContent = "评分中";
  setResultStatus(statusText, "ready");

  try {
    const response = await fetch("/api/grade-answer", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(collectPayload(config))
    });
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.message || result.error || "评分请求失败");
    }

    return result;
  } catch (error) {
    if (error.message === "grading_api_unavailable") {
      throw new Error("评分 API 暂不可用，请先启动 Python 服务。");
    }
    throw error;
  } finally {
    isSubmitting = false;
    elements.submitGradeBtn.textContent = "获取建议分";
    refreshSubmitState();
    updateAutoFlowControls();
  }
}

async function submitGrade(event) {
  event.preventDefault();

  if (isSubmitting || autoFlowState === "running") {
    return;
  }

  if (!croppedImage && mediaStream && cropRect) {
    captureCrop();
  }

  try {
    const result = await requestGradeResult();
    const autoAccepted = isAutoAccepted(result);
    renderResult(result, { autoAccepted });
    addHistoryItem(result, { autoAccepted: false, mode: "manual" });
  } catch (error) {
    renderError(error.message || "评分请求失败");
  }
}

function validateConfig(config) {
  if (!Number.isFinite(config.max_score) || config.max_score <= 0) {
    return "满分必须大于 0。";
  }
  if (!config.standard_answer) {
    return "请先填写标准答案。";
  }
  if (!config.grading_rules) {
    return "请先填写每步给分规则。";
  }
  return "";
}

function renderResult(result, options = {}) {
  const autoAccepted = Boolean(options.autoAccepted);
  elements.suggestedScore.textContent =
    result.suggested_score === null || result.suggested_score === undefined
      ? `待复核 / ${formatScore(result.max_score)}`
      : `${formatScore(result.suggested_score)} / ${formatScore(result.max_score)}`;
  elements.confidence.textContent = formatPercent(normalizeConfidenceRatio(result.confidence));
  elements.modelName.textContent = result.model || "--";
  renderList(elements.uncertainList, result.uncertain_factors, "无明显不确定因素");

  elements.reviewBadge.textContent = autoAccepted ? "高置信度" : result.needs_review ? "需要复核" : "可参考";
  elements.reviewBadge.dataset.state = autoAccepted ? "ready" : result.needs_review ? "warning" : "ready";
  elements.reviewReason.textContent = result.review_reason || "";
  if (autoAccepted) {
    setResultStatus(
      options.action === "score"
        ? `置信度达到 ${formatPercent(getConfidenceThreshold())}，准备自动点击。`
        : `置信度达到 ${formatPercent(getConfidenceThreshold())}，建议分可参考。`,
      "ready"
    );
  } else {
    setResultStatus("评分完成，请人工确认后再使用。", result.needs_review ? "warning" : "ready");
  }
}

function renderError(message) {
  elements.reviewBadge.textContent = "评分失败";
  elements.reviewBadge.dataset.state = "error";
  setResultStatus(message, "error");
}

function renderList(list, items, emptyText) {
  list.replaceChildren();
  const values = Array.isArray(items) && items.length ? items : [emptyText];

  for (const value of values) {
    const item = document.createElement("li");
    item.textContent = value;
    list.append(item);
  }
}

function addHistoryItem(result, options = {}) {
  const history = readStorage(HISTORY_KEY) || [];
  const item = {
    time: new Date().toISOString(),
    question_id: result.question_id || fields.questionId.value.trim() || "未填题号",
    suggested_score: result.suggested_score,
    max_score: result.max_score,
    confidence: result.confidence,
    needs_review: result.needs_review,
    review_reason: result.review_reason || "",
    auto_accepted: Boolean(options.autoAccepted),
    skipped: Boolean(options.skipped),
    needs_manual: Boolean(options.needsManual)
  };

  writeStorage(HISTORY_KEY, [item, ...history].slice(0, MAX_HISTORY_ITEMS));
  renderHistory();
}

function renderHistory() {
  const history = readStorage(HISTORY_KEY) || [];
  elements.historyList.replaceChildren();

  if (!history.length) {
    const empty = document.createElement("li");
    empty.className = "history-empty";
    empty.textContent = "暂无评分记录";
    elements.historyList.append(empty);
    return;
  }

  for (const item of history) {
    const row = document.createElement("li");
    row.className = "history-item";

    const main = document.createElement("strong");
    main.textContent = `${item.question_id} · ${
      item.suggested_score === null || item.suggested_score === undefined
        ? "待复核"
        : `${formatScore(item.suggested_score)} / ${formatScore(item.max_score)}`
    }`;

    const meta = document.createElement("span");
    const time = new Date(item.time);
    const state = item.skipped
      ? "自动跳过"
      : item.auto_accepted
        ? "自动打分"
        : item.needs_manual || item.needs_review
          ? "等待审核"
          : "可参考";
    meta.textContent = `${
      Number.isNaN(time.getTime()) ? "" : time.toLocaleTimeString()
    } · 置信度 ${formatPercent(normalizeConfidenceRatio(item.confidence))} · ${state}`;

    row.append(main, meta);
    elements.historyList.append(row);
  }
}

function clearConfig() {
  window.localStorage.removeItem(CONFIG_KEY);
  for (const field of Object.values(fields)) {
    if (field.type === "checkbox") {
      field.checked = true;
    } else {
      field.value = field.id === "maxScore" ? "6" : "";
    }
  }
  fields.scorePrecision.value = "0.5";
  elements.saveStatus.textContent = "已清空";
  refreshSubmitState();
  renderScoreClickGrid();
}

function clearHistory() {
  window.localStorage.removeItem(HISTORY_KEY);
  renderHistory();
}

function clearCroppedImage() {
  croppedImage = "";
  elements.cropCanvas.width = 0;
  elements.cropCanvas.height = 0;
  elements.cropEmpty.classList.remove("is-hidden");
}

function isAutoAccepted(result) {
  const confidence = normalizeConfidenceRatio(result.confidence);
  const suggestedScore = Number(result.suggested_score);
  return confidence >= getConfidenceThreshold() && !result.needs_review && Number.isFinite(suggestedScore);
}

function refreshSubmitState() {
  const config = collectConfig();
  elements.submitGradeBtn.disabled =
    isSubmitting ||
    autoFlowState === "running" ||
    !croppedImage ||
    Boolean(validateConfig(config));
}

function setCaptureStatus(message, state) {
  elements.captureStatus.textContent = message;
  elements.captureStatus.dataset.state = state;
}

function setResultStatus(message, state) {
  elements.resultStatus.textContent = message;
  elements.resultStatus.dataset.state = state;
}

function setClickStatus(message, state) {
  elements.clickStatus.textContent = message;
  elements.clickStatus.dataset.state = state;
}

function readStorage(key) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  window.localStorage.setItem(key, JSON.stringify(value));
}

function formatScore(value) {
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function normalizeConfidenceRatio(value) {
  const confidence = Number(value);
  if (!Number.isFinite(confidence)) {
    return 0;
  }
  if (confidence > 1 && confidence <= 100) {
    return confidence / 100;
  }
  return clamp(confidence, 0, 1);
}

function autoHoldMessage(result, suffix) {
  const confidence = normalizeConfidenceRatio(result.confidence);
  if (confidence < getConfidenceThreshold()) {
    return `置信度低于 ${formatPercent(getConfidenceThreshold())}，${suffix}`;
  }
  if (result.needs_review) {
    return `模型标记需要复核，${suffix}`;
  }
  return `未满足自动打分条件，${suffix}`;
}

function formatDelaySeconds(ms) {
  const seconds = normalizePageDelayMs(ms) / 1000;
  return Number(seconds.toFixed(1)).toLocaleString("zh-CN", { maximumFractionDigits: 1 });
}

function formatPoint(point) {
  return point ? `${point.x}, ${point.y}` : "未记录";
}

function scoreKey(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "";
  }
  return roundScore(number)
    .toFixed(2)
    .replace(/\.?0+$/, "");
}

function roundScore(value) {
  return Math.round(Number(value) * 100) / 100;
}

function roundScoreToPrecision(value) {
  const step = getScoreStep();
  return roundScore(Math.round(Number(value) / step) * step);
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function wait(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

for (const field of Object.values(fields)) {
  if (field.type === "file") {
    continue;
  }
  field.addEventListener("input", saveConfig);
  field.addEventListener("change", saveConfig);
}

elements.startCaptureBtn.addEventListener("click", startCapture);
elements.stopCaptureBtn.addEventListener("click", stopCapture);
elements.snapshotBtn.addEventListener("click", captureCrop);
elements.captureVideo.addEventListener("loadedmetadata", updatePreviewAspectRatio);
elements.captureVideo.addEventListener("resize", updatePreviewAspectRatio);
elements.selectionOverlay.addEventListener("pointerdown", beginSelection);
elements.selectionOverlay.addEventListener("pointermove", updateSelection);
elements.selectionOverlay.addEventListener("pointerup", endSelection);
elements.selectionOverlay.addEventListener("pointercancel", endSelection);
elements.gradingForm.addEventListener("submit", submitGrade);
elements.clearConfigBtn.addEventListener("click", clearConfig);
elements.clearHistoryBtn.addEventListener("click", clearHistory);
elements.autoClickEnabled.addEventListener("change", () => {
  clickConfig.enabled = elements.autoClickEnabled.checked;
  saveClickConfig();
});
elements.confidenceThreshold.addEventListener("input", saveClickConfig);
elements.lowConfidenceAction.addEventListener("change", saveClickConfig);
elements.pageRefreshDelayMs.addEventListener("input", saveClickConfig);
elements.refreshMouseBtn.addEventListener("click", refreshMousePosition);
elements.recordNextClickBtn.addEventListener("click", recordNextClickPoint);
elements.testNextClickBtn.addEventListener("click", testNextClickPoint);
elements.startAutoFlowBtn.addEventListener("click", startAutoFlow);
elements.pauseAutoFlowBtn.addEventListener("click", () => pauseAutoFlow());
elements.continueAutoFlowBtn.addEventListener("click", continueAutoFlow);
elements.refreshScoreClickGridBtn.addEventListener("click", renderScoreClickGrid);

loadConfig();
loadClickConfig();
renderHistory();
refreshSubmitState();
checkHealth();
