(function() {
    if (window.__thereseFormPasteGuard) return;
    window.__thereseFormPasteGuard = true;

    var SKIP_INPUT_TYPES = {
        hidden: 1, file: 1, checkbox: 1, radio: 1, submit: 1,
        button: 1, reset: 1, image: 1, range: 1, color: 1
    };

    var hinted = false;

    function firstCellFromText(text) {
        if (!text) return '';
        var raw = String(text).replace(/\u00a0/g, ' ').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        return raw.split('\n', 1)[0].split('\t', 1)[0].trim();
    }

    function firstCellFromHtml(html) {
        if (!html) return '';
        try {
            var doc = new DOMParser().parseFromString(html, 'text/html');
            var cell = doc.querySelector('td, th');
            if (cell) return (cell.textContent || '').replace(/\u00a0/g, ' ').trim();
            var block = doc.querySelector('p, li, h1, h2, h3, span, div');
            if (block) {
                var t = (block.textContent || '').replace(/\u00a0/g, ' ').trim();
                if (t) return t.split('\n', 1)[0].trim();
            }
            var body = (doc.body && doc.body.textContent) || '';
            return body.replace(/\u00a0/g, ' ').trim().split('\n', 1)[0].trim();
        } catch (err) {}
        return '';
    }

    function isOfficeHtml(html) {
        if (!html) return false;
        return /urn:schemas-microsoft-com|xmlns:o=|StartFragment|office:excel|office:word|class=["']?Mso|ProgId/i.test(html);
    }

    function looksLikeSpreadsheet(text, html) {
        if (html && /<table|<tr[\s>]|<td[\s>]/i.test(html)) return true;
        if (text && text.indexOf('\t') !== -1) return true;
        return false;
    }

    function looksLikeBlock(text, html) {
        if (looksLikeSpreadsheet(text, html)) return true;
        if (isOfficeHtml(html)) return true;
        if (html && (html.match(/<p[\s>]/gi) || []).length > 1) return true;
        if (!text) return false;
        var lines = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n').filter(function(ln) {
            return ln.trim();
        });
        return lines.length > 1;
    }

    function elementOf(el) {
        if (!el) return null;
        if (el.nodeType === 3) return el.parentElement;
        if (el.nodeType === 1) return el;
        return null;
    }

    function isEditableTarget(el) {
        if (!el || el.readOnly || el.disabled) return false;
        if (el.isContentEditable) return true;
        var tag = (el.tagName || '').toLowerCase();
        if (tag === 'textarea') return true;
        if (tag !== 'input') return false;
        var type = (el.type || 'text').toLowerCase();
        return !SKIP_INPUT_TYPES[type];
    }

    function isSelect(el) {
        return el && (el.tagName || '').toLowerCase() === 'select';
    }

    function isMultiline(el) {
        if (!el) return false;
        if (el.isContentEditable) return true;
        return (el.tagName || '').toLowerCase() === 'textarea';
    }

    function isExempt(el) {
        el = elementOf(el);
        if (!el || !el.closest) return false;
        if (el.closest('[data-allow-block-paste]')) return true;
        if (el.closest('textarea[name="pasted_data"]')) return true;
        if (el.closest('.tox, .tox-tinymce, .tox-edit-area, textarea.wysiwyg-editor')) return true;
        return false;
    }

    function isFileInput(el) {
        el = elementOf(el);
        if (!el) return false;
        if ((el.tagName || '').toLowerCase() === 'input' && (el.type || '').toLowerCase() === 'file') {
            return true;
        }
        if (el.closest && el.closest('input[type="file"]')) return true;
        if (el.closest) {
            var label = el.closest('label');
            if (label && label.control && (label.control.type || '').toLowerCase() === 'file') {
                return true;
            }
        }
        return false;
    }

    function hasFiles(dt) {
        if (!dt) return false;
        if (dt.files && dt.files.length) return true;
        var types = dt.types;
        if (!types) return false;
        if (typeof types.contains === 'function') return types.contains('Files');
        if (typeof types.includes === 'function') return types.includes('Files');
        for (var i = 0; i < types.length; i++) {
            if (types[i] === 'Files' || types[i] === 'application/x-moz-file') return true;
        }
        return false;
    }

    function resolveField(el, allowActive) {
        el = elementOf(el);
        if (el) {
            if (isEditableTarget(el) || isSelect(el)) return el;
            if (el.closest) {
                var host = el.closest('input, textarea, select, [contenteditable="true"]');
                if (host && (isEditableTarget(host) || isSelect(host))) return host;
                var label = el.closest('label');
                if (label && label.control && (isEditableTarget(label.control) || isSelect(label.control))) {
                    return label.control;
                }
            }
        }
        if (allowActive === false) return null;
        var active = document.activeElement;
        if (active && (isEditableTarget(active) || isSelect(active))) return active;
        return null;
    }

    function isDateField(el) {
        if (!el) return false;
        if (el.classList && el.classList.contains('date-picker')) return true;
        var name = el.name || el.id || '';
        return /date_of_birth|valid_from|valid_until|due_date|_date$/i.test(name);
    }

    function isDecimalField(el) {
        if (!el) return false;
        var name = el.name || el.id || '';
        return /weekly_hours|workhours_percentage|monthly_salary|percentage|amount|true_cost/i.test(name);
    }

    function parseDate(value) {
        if (typeof window.parseEuropeanDateInput === 'function') {
            return window.parseEuropeanDateInput(value);
        }
        return undefined;
    }

    function formatDate(d) {
        if (typeof window.formatEuropeanDate === 'function') {
            return window.formatEuropeanDate(d);
        }
        function pad(n) { return n < 10 ? '0' + n : String(n); }
        return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '.' + d.getFullYear();
    }

    function normalizeDecimal(value) {
        var text = firstCellFromText(value).replace(/\s/g, '');
        if (!text) return '';
        if (text.indexOf(',') !== -1 && text.indexOf('.') !== -1) {
            if (text.lastIndexOf(',') > text.lastIndexOf('.')) {
                text = text.replace(/\./g, '').replace(',', '.');
            } else {
                text = text.replace(/,/g, '');
            }
        } else if (text.indexOf(',') !== -1) {
            text = text.replace(',', '.');
        }
        return text;
    }

    function payloadFrom(dt) {
        if (!dt) return { text: '', html: '' };
        var text = '';
        var html = '';
        try { text = dt.getData('text/plain') || dt.getData('text') || ''; } catch (err) {}
        try { html = dt.getData('text/html') || ''; } catch (err2) {}
        return { text: text, html: html };
    }

    function insertAtCaret(el, value) {
        if (el.isContentEditable) {
            el.textContent = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            return;
        }
        var start = el.selectionStart;
        var end = el.selectionEnd;
        if (typeof start !== 'number' || typeof end !== 'number') {
            el.value = value;
        } else {
            var current = el.value || '';
            el.value = current.slice(0, start) + value + current.slice(end);
            var pos = start + value.length;
            try {
                el.setSelectionRange(pos, pos);
            } catch (err) {}
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function applyValue(el, raw, replace) {
        var value = raw;
        if (el.isContentEditable) {
            el.textContent = firstCellFromText(value);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            return;
        }
        if (isDateField(el)) {
            value = firstCellFromText(raw);
            var parsed = parseDate(value);
            if (parsed) {
                value = formatDate(parsed);
                el.value = value;
                if (el._flatpickr) {
                    el._flatpickr.setDate(parsed, true);
                    return;
                }
            } else {
                el.value = value;
            }
        } else if (isDecimalField(el) || (el.type || '').toLowerCase() === 'number') {
            el.value = normalizeDecimal(raw);
        } else if (replace) {
            el.value = firstCellFromText(raw);
        } else {
            insertAtCaret(el, raw);
            return;
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function showHint(anchor) {
        var form = (anchor && anchor.closest) ? anchor.closest('form') : null;
        var host = form || document.querySelector('main.content') || document.body;
        if (!host) return;
        var hint = host.querySelector('.form-paste-hint');
        if (!hint) {
            hint = document.createElement('p');
            hint.className = 'field-hint form-paste-hint';
            hint.setAttribute('role', 'status');
            host.insertBefore(hint, host.firstChild);
        }
        hint.textContent = 'Nur der erste Wert wurde eingefügt.';
        hint.hidden = false;
    }

    function cellFrom(payload) {
        return firstCellFromText(payload.text) || firstCellFromHtml(payload.html);
    }

    function shouldTruncate(field, payload) {
        if (!field || isMultiline(field)) {
            return looksLikeSpreadsheet(payload.text, payload.html);
        }
        return looksLikeBlock(payload.text, payload.html);
    }

    function handlePasteOrDrop(e, isDrop) {
        if (isExempt(e.target)) return;
        var dt = isDrop ? e.dataTransfer : e.clipboardData;
        if (isDrop && hasFiles(dt) && isFileInput(e.target)) return;

        var field = resolveField(e.target, isDrop ? false : true);
        if (field && isExempt(field)) return;

        var payload = payloadFrom(dt);

        if (isDrop) {
            e.preventDefault();
            if (e.stopPropagation) e.stopPropagation();
            if (hasFiles(dt)) return;
            if (!field || isSelect(field) || !isEditableTarget(field)) return;
            var dropTruncate = shouldTruncate(field, payload);
            var dropValue = dropTruncate ? cellFrom(payload) : (payload.text || cellFrom(payload));
            if (!dropValue) return;
            applyValue(field, dropValue, dropTruncate || !isMultiline(field));
            if (dropTruncate && !hinted) {
                hinted = true;
                showHint(field);
            }
            return;
        }

        if (!field || isSelect(field) || !isEditableTarget(field)) return;
        var block = looksLikeBlock(payload.text, payload.html);
        var spreadsheet = looksLikeSpreadsheet(payload.text, payload.html);
        var needsNorm = !isSelect(field) && isEditableTarget(field)
            && (isDateField(field) || isDecimalField(field) || (field.type || '').toLowerCase() === 'number');
        var truncate = isMultiline(field) ? spreadsheet : (block || needsNorm);
        if (!truncate && !needsNorm) return;
        if (isMultiline(field) && !spreadsheet && !needsNorm) return;

        e.preventDefault();
        if (e.stopPropagation) e.stopPropagation();
        var value = truncate ? cellFrom(payload) : (payload.text || cellFrom(payload));
        if (!value) return;
        applyValue(field, value, truncate || !isMultiline(field));
        if (truncate && !hinted) {
            hinted = true;
            showHint(field);
        }
    }

    function onDragOver(e) {
        if (isExempt(e.target)) return;
        if (hasFiles(e.dataTransfer) && isFileInput(e.target)) return;
        e.preventDefault();
        if (e.dataTransfer) {
            try { e.dataTransfer.dropEffect = hasFiles(e.dataTransfer) ? 'none' : 'copy'; } catch (err) {}
        }
    }

    document.addEventListener('paste', function(e) { handlePasteOrDrop(e, false); }, true);
    document.addEventListener('dragover', onDragOver, true);
    document.addEventListener('drop', function(e) { handlePasteOrDrop(e, true); }, true);
})();
