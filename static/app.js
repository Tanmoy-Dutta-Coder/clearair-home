/**
 * ClearAir Home - Client Application Logic
 * Pure Vanilla JS, zero dependencies, WCAG AA compliant.
 * Security: Uses textContent exclusively for all dynamic data; zero HTML parsing.
 */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("plan-form");
  const submitBtn = document.getElementById("submit-btn");
  const detectAqiBtn = document.getElementById("detect-aqi-btn");
  const useLocationBtn = document.getElementById("use-location-btn");
  const detectionStatus = document.getElementById("detection-status");
  const errorBox = document.getElementById("form-errors");
  const resultsSection = document.getElementById("results-section");
  const resultsHeading = document.getElementById("results-heading");
  const aiStatusPill = document.getElementById("ai-status-pill");
  const resultAqiVal = document.getElementById("result-aqi-val");
  const resultAqiBand = document.getElementById("result-aqi-band");
  const aqiBadgeContainer = document.querySelector(".aqi-badge-container");
  const resultSummary = document.getElementById("result-summary");
  const routineCardsContainer = document.getElementById("routine-cards");
  const indoorCardsContainer = document.getElementById("indoor-cards");
  const swapsCardsContainer = document.getElementById("swaps-cards");
  const locationInput = document.getElementById("location");
  const aqiInput = document.getElementById("aqi");

  // Feature detect browser geolocation in secure context (HTTPS or localhost)
  const isSecure = window.isSecureContext || window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  if (navigator.geolocation && isSecure && useLocationBtn) {
    useLocationBtn.classList.remove("hidden");
  }

  // Regional preset buttons handler with visual selected state
  const presetBtns = document.querySelectorAll(".preset-btn");
  presetBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      presetBtns.forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");

      const loc = btn.getAttribute("data-location");
      const aqi = btn.getAttribute("data-aqi");
      if (loc && aqi) {
        locationInput.value = loc;
        aqiInput.value = aqi;
        detectionStatus.classList.add("hidden");
        aqiInput.focus();
      }
    });
  });

  // AQI Auto-Detection By Place Button Handler
  detectAqiBtn.addEventListener("click", async () => {
    const loc = locationInput.value.trim();
    if (!loc || loc.length < 2) {
      detectionStatus.className = "detection-feedback error";
      detectionStatus.textContent = "⚠️ Please enter a location name first to detect AQI.";
      detectionStatus.classList.remove("hidden");
      locationInput.focus();
      return;
    }

    presetBtns.forEach((b) => b.classList.remove("selected"));
    detectAqiBtn.disabled = true;
    const originalText = detectAqiBtn.textContent;
    detectAqiBtn.textContent = "Detecting...";
    detectionStatus.className = "detection-feedback";
    detectionStatus.textContent = "Fetching modelled air quality estimates...";
    detectionStatus.classList.remove("hidden");

    const coldStartTimer = startColdStartTimer();
    try {
      const resp = await fetch("/api/aqi?place=" + encodeURIComponent(loc));
      if (resp.ok) {
        const data = await resp.json();
        aqiInput.value = data.aqi;
        const timeStr = data.observed_at || "recently";
        detectionStatus.className = "detection-feedback";
        detectionStatus.textContent = `Auto-detected from Open-Meteo (modelled estimate), ${timeStr}. You can edit this.`;
        aqiInput.focus();
      } else {
        detectionStatus.className = "detection-feedback error";
        detectionStatus.textContent = "⚠️ Couldn't detect AQI, please enter it manually.";
      }
    } catch (err) {
      detectionStatus.className = "detection-feedback error";
      detectionStatus.textContent = "⚠️ Couldn't detect AQI, please enter it manually.";
    } finally {
      clearColdStartTimer(coldStartTimer);
      detectAqiBtn.disabled = false;
      detectAqiBtn.textContent = originalText;
    }
  });

  // Browser Geolocation Detection Button Handler (Optional, user-triggered only)
  if (useLocationBtn) {
    useLocationBtn.addEventListener("click", () => {
      presetBtns.forEach((b) => b.classList.remove("selected"));
      useLocationBtn.disabled = true;
      detectionStatus.className = "detection-feedback";
      detectionStatus.textContent = "Detecting your location...";
      detectionStatus.classList.remove("hidden");

      navigator.geolocation.getCurrentPosition(
        async (position) => {
          const coldStartTimer = startColdStartTimer();
          try {
            // Round coordinates to 2 decimal places (~1 km grid) for privacy
            const lat = Math.round(position.coords.latitude * 100) / 100;
            const lon = Math.round(position.coords.longitude * 100) / 100;

            const resp = await fetch(`/api/aqi/coords?lat=${lat}&lon=${lon}`);
            if (resp.ok) {
              const data = await resp.json();
              aqiInput.value = data.aqi;
              if (!locationInput.value.trim()) {
                locationInput.value = "Your current location (approx.)";
              }
              const timeStr = data.observed_at || "recently";
              detectionStatus.className = "detection-feedback";
              detectionStatus.textContent = `Auto-detected near your current location from Open-Meteo (modelled estimate), ${timeStr}. You can edit this.`;
              aqiInput.focus();
            } else {
              detectionStatus.className = "detection-feedback error";
              detectionStatus.textContent = "⚠️ Couldn't fetch air quality for your area. Please enter your AQI manually.";
            }
          } catch (fetchErr) {
            detectionStatus.className = "detection-feedback error";
            detectionStatus.textContent = "⚠️ Couldn't fetch air quality for your area. Please enter your AQI manually.";
          } finally {
            clearColdStartTimer(coldStartTimer);
            useLocationBtn.disabled = false;
          }
        },
        (geoErr) => {
          useLocationBtn.disabled = false;
          detectionStatus.className = "detection-feedback error";
          switch (geoErr.code) {
            case 1: // PERMISSION_DENIED
              detectionStatus.textContent = "⚠️ Location access was declined. Please enter your AQI manually.";
              break;
            case 2: // POSITION_UNAVAILABLE
              detectionStatus.textContent = "⚠️ Your device could not determine your location. Please enter your AQI manually.";
              break;
            case 3: // TIMEOUT
              detectionStatus.textContent = "⚠️ Finding your location took too long. Please enter your AQI manually.";
              break;
            default:
              detectionStatus.textContent = "⚠️ Your device could not determine your location. Please enter your AQI manually.";
              break;
          }
          detectionStatus.classList.remove("hidden");
        },
        {
          enableHighAccuracy: false,
          timeout: 8000,
          maximumAge: 600000, // 10 minutes
        }
      );
    });
  }

  // Helper: Display errors cleanly and link with ARIA
  const WAKE_UP_MESSAGE = "Waking up the server, this can take up to a minute...";

  function startColdStartTimer() {
    return setTimeout(() => {
      detectionStatus.className = "detection-feedback";
      detectionStatus.textContent = WAKE_UP_MESSAGE;
      detectionStatus.classList.remove("hidden");
    }, 5000);
  }

  function clearColdStartTimer(timerId) {
    clearTimeout(timerId);
    if (detectionStatus.textContent === WAKE_UP_MESSAGE) {
      detectionStatus.classList.add("hidden");
    }
  }

  function showError(message) {
    while (errorBox.firstChild) {
      errorBox.removeChild(errorBox.firstChild);
    }
    const p = document.createElement("p");
    p.textContent = message;
    errorBox.appendChild(p);
    errorBox.classList.remove("hidden");
    errorBox.focus();
  }

  function clearError() {
    while (errorBox.firstChild) {
      errorBox.removeChild(errorBox.firstChild);
    }
    errorBox.classList.add("hidden");
  }

  // Helper: Get Stepped Scale metadata for AQI band (Pattern symbol + class)
  function getBandInfo(band) {
    const normalized = (band || "").toLowerCase().trim();
    if (normalized === "good") {
      return { className: "band-good", label: "● Good" };
    }
    if (normalized === "satisfactory") {
      return { className: "band-satisfactory", label: "● Satisfactory" };
    }
    if (normalized === "moderate") {
      return { className: "band-moderate", label: "▲ Moderate" };
    }
    if (normalized === "poor") {
      return { className: "band-poor", label: "■ Poor" };
    }
    if (normalized === "very poor") {
      return { className: "band-very-poor", label: "◆ Very Poor" };
    }
    return { className: "band-severe", label: "✖ Severe" };
  }

  // Helper: Classify impact into High, Medium, or Low tier
  function getImpactTier(impactStr) {
    const text = (impactStr || "").toLowerCase();
    if (
      text.includes("95%") ||
      text.includes("92%") ||
      text.includes("90%") ||
      text.includes("85%") ||
      text.includes("80%") ||
      text.includes("75%") ||
      text.includes("70%")
    ) {
      return { label: "High impact", className: "tier-high" };
    }
    if (
      text.includes("15%") ||
      text.includes("20%") ||
      text.includes("25%") ||
      text.includes("30%")
    ) {
      return { label: "Low impact", className: "tier-low" };
    }
    return { label: "Medium impact", className: "tier-medium" };
  }

  // Helper: Create an Action Card using textContent only (0% XSS risk)
  function createActionCard(item) {
    const card = document.createElement("article");
    card.className = "action-card";

    const title = document.createElement("h4");
    title.textContent = item.action;

    const whyP = document.createElement("p");
    whyP.textContent = item.why;

    // Structured Impact Container with Text Tier Badge
    const impactContainer = document.createElement("div");
    impactContainer.className = "impact-container";

    const impactHeader = document.createElement("div");
    impactHeader.className = "impact-header";

    const tierInfo = getImpactTier(item.impact);
    const tierBadge = document.createElement("span");
    tierBadge.className = `impact-tier-badge ${tierInfo.className}`;
    tierBadge.textContent = tierInfo.label;

    impactHeader.appendChild(tierBadge);

    const impactDetail = document.createElement("p");
    impactDetail.className = "impact-detail";
    impactDetail.textContent = item.impact;

    impactContainer.appendChild(impactHeader);
    impactContainer.appendChild(impactDetail);

    card.appendChild(title);
    card.appendChild(whyP);
    card.appendChild(impactContainer);

    return card;
  }

  // Populate Section Cards safely
  function populateSection(container, items) {
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
    if (!items || items.length === 0) {
      const emptyP = document.createElement("p");
      emptyP.textContent = "No specific actions recommended for this section.";
      container.appendChild(emptyP);
      return;
    }
    items.forEach((item) => {
      container.appendChild(createActionCard(item));
    });
  }

  // Handle Form Submission
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();

    // 1. Gather & validate client inputs
    const locationVal = locationInput.value.trim();
    const aqiVal = parseInt(aqiInput.value, 10);
    const householdVal = document.getElementById("household").value;
    const commuteVal = document.getElementById("commute").value;
    const cookingFuelVal = document.getElementById("cooking_fuel").value;
    const budgetVal = document.getElementById("budget").value;

    const healthFactorCheckboxes = document.querySelectorAll('input[name="health_factors"]:checked');
    const healthFactorsVal = Array.from(healthFactorCheckboxes).map((cb) => cb.value);

    // Basic client validation
    if (!locationVal) {
      showError("Please enter your location or city name.");
      locationInput.focus();
      return;
    }
    if (locationVal.length > 80) {
      showError("Location name cannot exceed 80 characters.");
      locationInput.focus();
      return;
    }
    if (isNaN(aqiVal) || aqiVal < 0 || aqiVal > 500) {
      showError("Please enter a valid Indian AQI value between 0 and 500.");
      aqiInput.focus();
      return;
    }

    const payload = {
      location: locationVal,
      aqi: aqiVal,
      household: householdVal,
      health_factors: healthFactorsVal,
      commute: commuteVal,
      cooking_fuel: cookingFuelVal,
      budget: budgetVal,
    };

    // 2. Debounce and set loading state
    submitBtn.disabled = true;
    const originalBtnText = submitBtn.textContent;
    submitBtn.textContent = "Analyzing & Personalizing Plan...";
    const coldStartTimer = startColdStartTimer();

    try {
      const response = await fetch("/api/plan", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        if (response.status === 422) {
          const errData = await response.json();
          const detailMsg = (errData.errors && errData.errors.join("; ")) || errData.detail || "Validation error.";
          showError("Input error: " + detailMsg);
        } else if (response.status === 429) {
          showError("Too many requests. Please wait a minute before submitting again.");
        } else if (response.status === 413) {
          showError("Request payload was too large. Please shorten your input.");
        } else {
          showError("Unable to generate plan right now (Server error " + response.status + "). Please try again.");
        }
        return;
      }

      const plan = await response.json();

      // 3. Render Results safely using textContent
      resultAqiVal.textContent = String(payload.aqi);

      // Apply stepped scale with text label + pattern symbol (never color alone)
      const bandInfo = getBandInfo(plan.aqi_band);
      resultAqiBand.textContent = bandInfo.label;
      aqiBadgeContainer.className = `aqi-badge-container ${bandInfo.className}`;

      resultSummary.textContent = plan.summary;

      // AI Status Pill
      while (aiStatusPill.firstChild) {
        aiStatusPill.removeChild(aiStatusPill.firstChild);
      }
      if (plan.used_ai) {
        aiStatusPill.className = "status-pill pill-ai";
        aiStatusPill.textContent = "✨ Personalized with Google Gemini";
      } else {
        aiStatusPill.className = "status-pill pill-deterministic";
        aiStatusPill.textContent = "🛡️ Verified Baseline Protection Plan (Offline/Standard)";
      }

      // Populate cards in each section
      populateSection(routineCardsContainer, plan.routine);
      populateSection(indoorCardsContainer, plan.indoor);
      populateSection(swapsCardsContainer, plan.swaps);

      // Reveal results section
      resultsSection.classList.remove("hidden");

      // Accessibility: Shift programmatic focus to results heading
      resultsHeading.focus();
      resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });

    } catch (networkErr) {
      showError("Connection failed: Could not reach the ClearAir service. Please check your network and try again.");
    } finally {
      clearColdStartTimer(coldStartTimer);
      submitBtn.disabled = false;
      submitBtn.textContent = originalBtnText;
    }
  });
});
