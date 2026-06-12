const CONFIG_KEY = "exam-grading-assistant:question-config:v1";
const CROP_KEY = "exam-grading-assistant:crop-box:v1";
const HISTORY_KEY = "exam-grading-assistant:history:v1";
const MAX_HISTORY_ITEMS = 8;

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
  privacyConfirm: document.querySelector("#privacyConfirm"),
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
  answerSummary: document.querySelector("#answerSummary"),
  deductionList: document.querySelector("#deductionList"),
  uncertainList: document.querySelector("#uncertainList"),
  reviewReason: document.querySelector("#reviewReason"),
  historyList: document.querySelector("#historyList")
};

const fields = {
  questionId: document.querySelector("#questionId"),
  maxScore: document.querySelector("#maxScore"),
  scorePrecision: document.querySelector("#scorePrecision"),
  ruleVersion: document.querySelector("#ruleVersion"),
  standardAnswer: document.querySelector("#standardAnswer"),
  standardAnswerImage: document.querySelector("#standardAnswerImage"),
  gradingRules: document.querySelector("#gradingRules"),
  gradingRulesImage: document.querySelector("#gradingRulesImage"),
  deductionRules: document.querySelector("#deductionRules"),
  allowEquivalentAnswers: document.querySelector("#allowEquivalentAnswers"),
  scoreBySteps: document.querySelector("#scoreBySteps")
};

let mediaStream = null;
let cropRect = null;
let croppedImage = "";
const referenceImages = {
  standard_answer_image: null,
  grading_rules_image: null
};
let dragStart = null;
let isSubmitting = false;

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
  restoreCropBox();
  refreshSubmitState();
}

function stopCapture() {
  if (mediaStream) {
    for (const track of mediaStream.getTracks()) {
      track.stop();
    }
  }

  mediaStream = null;
  elements.captureVideo.srcObject = null;
  elements.previewEmpty.classList.remove("is-hidden");
  elements.startCaptureBtn.disabled = false;
  elements.snapshotBtn.disabled = true;
  elements.stopCaptureBtn.disabled = true;
  clearCroppedImage();
  setCaptureStatus("捕获已停止。", "warning");
  refreshSubmitState();
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
  if (!mediaStream || !cropRect || !elements.captureVideo.videoWidth || !elements.captureVideo.videoHeight) {
    setCaptureStatus("请先捕获画面并框选答案区域。", "warning");
    refreshSubmitState();
    return;
  }

  const frameBounds = elements.previewFrame.getBoundingClientRect();
  const scaleX = elements.captureVideo.videoWidth / frameBounds.width;
  const scaleY = elements.captureVideo.videoHeight / frameBounds.height;
  const sourceX = Math.round(cropRect.x * scaleX);
  const sourceY = Math.round(cropRect.y * scaleY);
  const sourceWidth = Math.round(cropRect.width * scaleX);
  const sourceHeight = Math.round(cropRect.height * scaleY);

  if (sourceWidth <= 0 || sourceHeight <= 0) {
    setCaptureStatus("裁剪区域无效，请重新框选。", "error");
    refreshSubmitState();
    return;
  }

  elements.cropCanvas.width = sourceWidth;
  elements.cropCanvas.height = sourceHeight;
  const context = elements.cropCanvas.getContext("2d", { willReadFrequently: false });
  context.drawImage(
    elements.captureVideo,
    sourceX,
    sourceY,
    sourceWidth,
    sourceHeight,
    0,
    0,
    sourceWidth,
    sourceHeight
  );

  croppedImage = elements.cropCanvas.toDataURL("image/png");
  elements.privacyConfirm.checked = false;
  elements.cropEmpty.classList.add("is-hidden");
  elements.cropSize.textContent = `裁剪图 ${sourceWidth} × ${sourceHeight} px`;
  setCaptureStatus("裁剪图已更新，提交前请确认不含学生身份信息。", "ready");
  refreshSubmitState();
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
    image: croppedImage,
    standard_answer_image: referenceImages.standard_answer_image?.dataUri || null,
    grading_rules_image: referenceImages.grading_rules_image?.dataUri || null
  };
}

async function submitGrade(event) {
  event.preventDefault();

  if (isSubmitting || !croppedImage) {
    return;
  }

  if (!elements.privacyConfirm.checked) {
    setResultStatus("请先确认裁剪图不含学生身份信息。", "warning");
    refreshSubmitState();
    return;
  }

  const config = collectConfig();
  const validationMessage = validateConfig(config);
  if (validationMessage) {
    setResultStatus(validationMessage, "error");
    return;
  }

  isSubmitting = true;
  elements.submitGradeBtn.disabled = true;
  elements.submitGradeBtn.textContent = "评分中";
  setResultStatus("正在请求评分 API。", "ready");

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

    renderResult(result);
    addHistoryItem(result);
  } catch (error) {
    const message =
      error.message === "grading_api_unavailable"
        ? "评分 API 暂不可用，请先启动 Python 服务。"
        : error.message || "评分请求失败";
    renderError(message);
  } finally {
    isSubmitting = false;
    elements.submitGradeBtn.textContent = "获取建议分";
    refreshSubmitState();
  }
}

function validateConfig(config) {
  if (!Number.isFinite(config.max_score) || config.max_score <= 0) {
    return "满分必须大于 0。";
  }
  if (!config.standard_answer && !referenceImages.standard_answer_image) {
    return "请填写标准答案，或选择标准答案图片。";
  }
  if (!config.grading_rules && !referenceImages.grading_rules_image) {
    return "请填写给分规则，或选择给分规则图片。";
  }
  return "";
}

function renderResult(result) {
  elements.suggestedScore.textContent =
    result.suggested_score === null || result.suggested_score === undefined
      ? `待复核 / ${formatScore(result.max_score)}`
      : `${formatScore(result.suggested_score)} / ${formatScore(result.max_score)}`;
  elements.confidence.textContent = `${Math.round((result.confidence || 0) * 100)}%`;
  elements.modelName.textContent = result.model || "--";
  elements.answerSummary.textContent = result.student_answer_summary || "未返回摘要";
  renderList(elements.deductionList, result.deduction_points, "无明确扣分点");
  renderList(elements.uncertainList, result.uncertain_factors, "无明显不确定因素");

  elements.reviewBadge.textContent = result.needs_review ? "需要复核" : "可参考";
  elements.reviewBadge.dataset.state = result.needs_review ? "warning" : "ready";
  elements.reviewReason.textContent = result.review_reason || "";
  setResultStatus("评分完成，老师仍需自行确认并手动录分。", result.needs_review ? "warning" : "ready");
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

function addHistoryItem(result) {
  const history = readStorage(HISTORY_KEY) || [];
  const item = {
    time: new Date().toISOString(),
    question_id: result.question_id || fields.questionId.value.trim() || "未填题号",
    suggested_score: result.suggested_score,
    max_score: result.max_score,
    confidence: result.confidence,
    needs_review: result.needs_review,
    review_reason: result.review_reason || ""
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
    meta.textContent = `${Number.isNaN(time.getTime()) ? "" : time.toLocaleTimeString()} · 置信度 ${Math.round(
      (item.confidence || 0) * 100
    )}% · ${item.needs_review ? "需要复核" : "可参考"}`;

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
  clearReferenceImage("standard_answer_image");
  clearReferenceImage("grading_rules_image");
  fields.scorePrecision.value = "0.5";
  elements.saveStatus.textContent = "已清空";
  refreshSubmitState();
}

function clearHistory() {
  window.localStorage.removeItem(HISTORY_KEY);
  renderHistory();
}

function clearCroppedImage() {
  croppedImage = "";
  elements.privacyConfirm.checked = false;
  elements.cropCanvas.width = 0;
  elements.cropCanvas.height = 0;
  elements.cropEmpty.classList.remove("is-hidden");
}

function refreshSubmitState() {
  const config = collectConfig();
  elements.submitGradeBtn.disabled =
    isSubmitting ||
    !croppedImage ||
    !elements.privacyConfirm.checked ||
    Boolean(validateConfig(config));
}

async function handleReferenceImageChange(event, key) {
  const file = event.target.files?.[0];
  if (!file) {
    clearReferenceImage(key);
    return;
  }

  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
    setResultStatus("参考图片只支持 PNG、JPEG 或 WebP。", "error");
    clearReferenceImage(key);
    return;
  }

  try {
    const dataUri = await readFileAsDataUri(file);
    referenceImages[key] = {
      dataUri,
      name: file.name,
      size: file.size,
      type: file.type
    };
    renderReferenceImage(key);
    refreshSubmitState();
  } catch {
    setResultStatus("参考图片读取失败，请重新选择。", "error");
    clearReferenceImage(key);
  }
}

function renderReferenceImage(key) {
  const reference = getReferenceElements(key);
  const image = referenceImages[key];
  if (!image) {
    reference.preview.classList.add("is-hidden");
    reference.previewImg.removeAttribute("src");
    reference.meta.textContent = "";
    reference.removeBtn.disabled = true;
    return;
  }

  reference.preview.classList.remove("is-hidden");
  reference.previewImg.src = image.dataUri;
  reference.meta.textContent = `${image.name} · ${formatBytes(image.size)}`;
  reference.removeBtn.disabled = false;
}

function clearReferenceImage(key) {
  referenceImages[key] = null;
  const reference = getReferenceElements(key);
  reference.input.value = "";
  renderReferenceImage(key);
  refreshSubmitState();
}

function getReferenceElements(key) {
  if (key === "standard_answer_image") {
    return {
      input: fields.standardAnswerImage,
      preview: document.querySelector("#standardAnswerImagePreview"),
      previewImg: document.querySelector("#standardAnswerImagePreviewImg"),
      meta: document.querySelector("#standardAnswerImageMeta"),
      removeBtn: document.querySelector("#removeStandardAnswerImageBtn")
    };
  }

  return {
    input: fields.gradingRulesImage,
    preview: document.querySelector("#gradingRulesImagePreview"),
    previewImg: document.querySelector("#gradingRulesImagePreviewImg"),
    meta: document.querySelector("#gradingRulesImageMeta"),
    removeBtn: document.querySelector("#removeGradingRulesImageBtn")
  };
}

function readFileAsDataUri(file) {
  return new Promise((resolveRead, rejectRead) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolveRead(reader.result));
    reader.addEventListener("error", rejectRead);
    reader.readAsDataURL(file);
  });
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function setCaptureStatus(message, state) {
  elements.captureStatus.textContent = message;
  elements.captureStatus.dataset.state = state;
}

function setResultStatus(message, state) {
  elements.resultStatus.textContent = message;
  elements.resultStatus.dataset.state = state;
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

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
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
elements.selectionOverlay.addEventListener("pointerdown", beginSelection);
elements.selectionOverlay.addEventListener("pointermove", updateSelection);
elements.selectionOverlay.addEventListener("pointerup", endSelection);
elements.selectionOverlay.addEventListener("pointercancel", endSelection);
elements.privacyConfirm.addEventListener("change", refreshSubmitState);
elements.gradingForm.addEventListener("submit", submitGrade);
elements.clearConfigBtn.addEventListener("click", clearConfig);
elements.clearHistoryBtn.addEventListener("click", clearHistory);
fields.standardAnswerImage.addEventListener("change", (event) =>
  handleReferenceImageChange(event, "standard_answer_image")
);
fields.gradingRulesImage.addEventListener("change", (event) =>
  handleReferenceImageChange(event, "grading_rules_image")
);
document
  .querySelector("#removeStandardAnswerImageBtn")
  .addEventListener("click", () => clearReferenceImage("standard_answer_image"));
document
  .querySelector("#removeGradingRulesImageBtn")
  .addEventListener("click", () => clearReferenceImage("grading_rules_image"));

loadConfig();
renderHistory();
refreshSubmitState();
checkHealth();
