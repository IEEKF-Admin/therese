(function() {
    var SKIP_INPUT_TYPES = {
        hidden: 1, file: 1, checkbox: 1, radio: 1, submit: 1,
        button: 1, reset: 1, image: 1, range: 1, color: 1
    };

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

    function looksLikeBlock(text, html) {
        if (html && /<table|<tr[\s>]|<td[\s>]/i.test(html)) return true;
        if (isOfficeHtml(html)) return true;
        if (html && (html.match(/<p[\s>]/gi) || []).length > 1) return true;
        if (!text) return false;
        if (text.indexOf('\t') !== -1) return true;
        var lines = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n').filter(function(ln) {
            return ln.trim();
        });
        return lines.length > 1;
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

    function resolveField(form, el) {
        if (!el) el = document.activeElement;
        if (el && el.nodeType === 3) el = el.parentElement;
        if (el && form.contains(el)) {
            if (isEditableTarget(el) || isSelect(el)) return el;
            if (el.closest) {
                var host = el.closest('input, textarea, select, [contenteditable="true"]');
                if (host && form.contains(host) && (isEditableTarget(host) || isSelect(host))) {
                    return host;
                }
            }
        }
        var active = document.activeElement;
        if (active && form.contains(active) && (isEditableTarget(active) || isSelect(active))) {
            return active;
        }
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

    function applyValue(el, raw) {
        var value = firstCellFromText(raw);
        if (el.isContentEditable) {
            el.textContent = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            return;
        }
        if (isDateField(el)) {
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
            el.value = normalizeDecimal(value);
        } else {
            el.value = value;
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function showHint(form) {
        var hint = form.querySelector('#employee-paste-hint');
        if (!hint) {
            hint = document.createElement('p');
            hint.id = 'employee-paste-hint';
            hint.className = 'field-hint';
            hint.setAttribute('role', 'status');
            form.insertBefore(hint, form.firstChild);
        }
        hint.textContent = 'Nur der erste Wert wurde eingefügt.';
        hint.hidden = false;
    }

    function bind(form) {
        var hinted = false;
        form.addEventListener('paste', function(e) {
            var text = '';
            var html = '';
            if (e.clipboardData) {
                text = e.clipboardData.getData('text/plain') || '';
                html = e.clipboardData.getData('text/html') || '';
            }
            var field = resolveField(form, e.target);
            var block = looksLikeBlock(text, html);
            var needsNorm = field && !isSelect(field) && isEditableTarget(field)
                && (isDateField(field) || isDecimalField(field) || (field.type || '').toLowerCase() === 'number');
            if (!block && !needsNorm) return;
            e.preventDefault();
            e.stopPropagation();
            if (!field || isSelect(field) || !isEditableTarget(field)) {
                if (block && !hinted) {
                    hinted = true;
                    showHint(form);
                }
                return;
            }
            var cell = firstCellFromText(text) || firstCellFromHtml(html);
            applyValue(field, cell);
            if (block && !hinted) {
                hinted = true;
                showHint(form);
            }
        }, true);
    }

    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('form.employee-form').forEach(bind);
    });
})();
