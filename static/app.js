/* Crane drawing generator UI. Live preview via POST /api/preview,
   save/load/edit/delete via /api/designs. No external dependencies. */
(function () {
  "use strict";

  var form = document.getElementById("crane-form");
  var drawingEl = document.getElementById("drawing");
  var warningsEl = document.getElementById("warnings");
  var tableBody = document.querySelector("#derived-table tbody");
  var badgeEl = document.getElementById("deflection-badge");
  var savedListEl = document.getElementById("saved-list");
  var savedEmptyEl = document.getElementById("saved-empty");
  var toastEl = document.getElementById("toast");
  var deleteBtn = document.getElementById("delete-btn");
  var loadedNote = document.getElementById("loaded-note");
  var saveBtn = document.getElementById("save-btn");

  var currentId = null;      // id of the saved design currently loaded
  var currentSvg = "";       // latest preview SVG text
  var previewTimer = null;
  var toastTimer = null;

  var NUMERIC_FIELDS = ["span_m", "capacity_t", "lift_height_m", "trolley_position_m"];

  function showToast(message, isError) {
    toastEl.textContent = message;
    toastEl.className = "toast show" + (isError ? " error" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.className = "toast"; }, 3500);
  }

  function readInputs() {
    var inputs = {
      name: document.getElementById("name").value,
      duty_class: document.getElementById("duty_class").value,
      notes: document.getElementById("notes").value
    };
    NUMERIC_FIELDS.forEach(function (field) {
      var raw = document.getElementById(field).value;
      if (raw === "" || raw === null) {
        if (field === "trolley_position_m") { return; } // optional, server defaults
        inputs[field] = raw;
        return;
      }
      inputs[field] = parseFloat(raw);
    });
    return inputs;
  }

  function clearErrors() {
    document.querySelectorAll(".error").forEach(function (el) { el.textContent = ""; });
  }

  function showErrors(errors) {
    clearErrors();
    Object.keys(errors).forEach(function (field) {
      var el = document.getElementById("err-" + field);
      if (el) { el.textContent = errors[field]; }
    });
  }

  var ROWS = [
    ["girder_depth_m", "Girder depth", "m", false],
    ["girder_width_m", "Girder width", "m", false],
    ["plate_t_mm", "Girder plate thickness", "mm", false],
    ["headroom_m", "Headroom (hoist + block)", "m", true],
    ["hook_block_h_m", "Hook block height", "m", true],
    ["end_carriage_h_m", "End carriage height", "m", true],
    ["girder_bottom_m", "Girder bottom above floor", "m", false],
    ["rail_top_m", "Rail top above floor", "m", false],
    ["trolley_h_m", "Trolley height", "m", true],
    ["overall_height_m", "Overall height", "m", false],
    ["overall_width_m", "Overall width", "m", false],
    ["end_carriage_len_m", "End carriage length", "m", false],
    ["trolley_w_m", "Trolley width", "m", true],
    ["trolley_travel_m", "Trolley travel", "m", true],
    ["approach_m", "Hook approach", "m", true],
    ["overhang_m", "Overhang each side", "m", true],
    ["deflection_live_mm", "Live-load deflection", "mm", false],
    ["deflection_limit_mm", "Deflection limit (L/750)", "mm", false],
    ["total_mass_kg", "Total mass (estimate)", "kg", true],
    ["max_wheel_load_kn", "Max wheel load", "kN", true]
  ];

  function renderDerived(derived) {
    var html = "";
    ROWS.forEach(function (row) {
      var key = row[0], label = row[1], unit = row[2], isEst = row[3];
      var value = derived[key];
      if (value === undefined) { return; }
      html += "<tr><td>" + label + "</td><td>" + value + " " + unit +
        (isEst ? ' <span class="est">(estimate)</span>' : "") + "</td></tr>";
    });
    tableBody.innerHTML = html;
    if (derived.deflection_ok) {
      badgeEl.textContent = "Deflection: PASS (" + derived.deflection_live_mm +
        " mm vs limit " + derived.deflection_limit_mm + " mm)";
      badgeEl.className = "badge pass";
    } else {
      badgeEl.textContent = "Deflection: FAIL (" + derived.deflection_live_mm +
        " mm vs limit " + derived.deflection_limit_mm + " mm)";
      badgeEl.className = "badge fail";
    }
  }

  function requestPreview() {
    var inputs = readInputs();
    fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(inputs)
    }).then(function (resp) { return resp.json().then(function (data) { return { status: resp.status, data: data }; }); })
      .then(function (result) {
        if (result.status !== 200) {
          if (result.data.errors) { showErrors(result.data.errors); }
          drawingEl.textContent = "Preview unavailable. Fix the highlighted inputs.";
          return;
        }
        clearErrors();
        currentSvg = result.data.svg;
        drawingEl.innerHTML = currentSvg;
        renderDerived(result.data.derived);
        warningsEl.innerHTML = "";
        (result.data.warnings || []).forEach(function (w) {
          var div = document.createElement("div");
          div.className = "warning";
          div.textContent = w;
          warningsEl.appendChild(div);
        });
      })
      .catch(function () {
        drawingEl.textContent = "Could not reach the server.";
      });
  }

  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(requestPreview, 300);
  }

  // Keep number inputs and range sliders in sync, then preview.
  NUMERIC_FIELDS.forEach(function (field) {
    var num = document.getElementById(field);
    var range = document.getElementById(field + "-range");
    var val = document.getElementById("val-" + field);
    if (!range) { return; }
    range.addEventListener("input", function () {
      num.value = range.value;
      val.textContent = parseFloat(range.value).toFixed(2);
      schedulePreview();
    });
    num.addEventListener("input", function () {
      var v = parseFloat(num.value);
      if (!isNaN(v)) {
        range.value = Math.min(Math.max(v, parseFloat(range.min)), parseFloat(range.max));
        val.textContent = v.toFixed(2);
      }
      schedulePreview();
    });
  });

  document.getElementById("name").addEventListener("input", schedulePreview);
  document.getElementById("duty_class").addEventListener("change", schedulePreview);
  document.getElementById("notes").addEventListener("input", schedulePreview);

  function loadSavedList() {
    fetch("/api/designs").then(function (resp) { return resp.json(); })
      .then(function (data) {
        var designs = data.designs || [];
        savedEmptyEl.hidden = designs.length > 0;
        savedListEl.innerHTML = "";
        designs.forEach(function (d) {
          var li = document.createElement("li");
          if (d.id === currentId) { li.className = "active"; }
          var nameDiv = document.createElement("div");
          nameDiv.className = "s-name";
          nameDiv.textContent = d.name;
          var metaDiv = document.createElement("div");
          metaDiv.className = "s-meta";
          metaDiv.textContent = "Span " + d.span_m + " m, " + d.capacity_t +
            " t, " + d.duty_class + " | updated " +
            new Date(d.updated_at).toLocaleString();
          li.appendChild(nameDiv);
          li.appendChild(metaDiv);
          li.addEventListener("click", function () { loadDesign(d.id); });
          savedListEl.appendChild(li);
        });
      });
  }

  function fillForm(inputs) {
    document.getElementById("name").value = inputs.name;
    document.getElementById("span_m").value = inputs.span_m;
    document.getElementById("capacity_t").value = inputs.capacity_t;
    document.getElementById("lift_height_m").value = inputs.lift_height_m;
    document.getElementById("trolley_position_m").value = inputs.trolley_position_m;
    document.getElementById("duty_class").value = inputs.duty_class;
    document.getElementById("notes").value = inputs.notes || "";
    NUMERIC_FIELDS.forEach(function (field) {
      var range = document.getElementById(field + "-range");
      var val = document.getElementById("val-" + field);
      var v = parseFloat(document.getElementById(field).value);
      if (range && !isNaN(v)) {
        range.value = Math.min(Math.max(v, parseFloat(range.min)), parseFloat(range.max));
        val.textContent = v.toFixed(2);
      }
    });
  }

  function setLoaded(id, name) {
    currentId = id;
    deleteBtn.disabled = !id;
    saveBtn.textContent = id ? "Update design" : "Save design";
    if (id) {
      loadedNote.hidden = false;
      loadedNote.textContent = "Editing saved design: " + name + " (id " + id + ").";
    } else {
      loadedNote.hidden = true;
    }
    loadSavedList();
  }

  function loadDesign(id) {
    fetch("/api/designs/" + id).then(function (resp) {
      if (resp.status === 404) { showToast("Design not found.", true); return null; }
      return resp.json();
    }).then(function (design) {
      if (!design) { return; }
      fillForm(design.inputs);
      setLoaded(design.id, design.inputs.name);
      requestPreview();
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var inputs = readInputs();
    var method = currentId ? "PUT" : "POST";
    var url = currentId ? "/api/designs/" + currentId : "/api/designs";
    fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(inputs)
    }).then(function (resp) { return resp.json().then(function (data) { return { status: resp.status, data: data }; }); })
      .then(function (result) {
        if (result.status === 400 && result.data.errors) {
          showErrors(result.data.errors);
          showToast("Please fix the highlighted inputs.", true);
          return;
        }
        if (result.status !== 200 && result.status !== 201) {
          showToast(result.data.error || "Save failed.", true);
          return;
        }
        clearErrors();
        setLoaded(result.data.id, result.data.inputs.name);
        showToast("Saved.");
        requestPreview();
      })
      .catch(function () { showToast("Could not reach the server.", true); });
  });

  document.getElementById("new-btn").addEventListener("click", function () {
    form.reset();
    document.getElementById("duty_class").value = "A4";
    setLoaded(null);
    NUMERIC_FIELDS.forEach(function (field) {
      var range = document.getElementById(field + "-range");
      var val = document.getElementById("val-" + field);
      var v = parseFloat(document.getElementById(field).value);
      if (range && !isNaN(v)) {
        range.value = v;
        val.textContent = v.toFixed(2);
      }
    });
    requestPreview();
  });

  document.getElementById("export-btn").addEventListener("click", function () {
    if (!currentSvg) { showToast("No drawing to export yet.", true); return; }
    var blob = new Blob([currentSvg], { type: "image/svg+xml" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "crane-drawing.svg";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  });

  deleteBtn.addEventListener("click", function () {
    if (!currentId) { return; }
    if (!confirm("Delete this saved design? This cannot be undone.")) { return; }
    fetch("/api/designs/" + currentId, { method: "DELETE" })
      .then(function (resp) {
        if (resp.status === 404) { showToast("Design not found.", true); return; }
        if (resp.status !== 204) { showToast("Delete failed.", true); return; }
        showToast("Design deleted.");
        form.reset();
        document.getElementById("duty_class").value = "A4";
        setLoaded(null);
        requestPreview();
      });
  });

  loadSavedList();
  requestPreview();
})();
