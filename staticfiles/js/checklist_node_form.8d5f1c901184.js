(function() {
    const FIELD_GROUPS = {
        field_type: ['field'],
        choice_key: ['radio_option'],
        label: ['section', 'field', 'html', 'radio_option'],
        content: ['html'],
        field_help: ['field'],
        help_fields: ['html', 'field'],
        required: ['field'],
        field_advanced: ['field'],
        visible_subject: ['field', 'html'],
        field_file: ['field'],
        field_acknowledge: ['field'],
    };

    const FIELD_TYPE_GROUPS = {
        field_file: ['file'],
        field_acknowledge: ['acknowledge'],
    };

    const ACKNOWLEDGE_LABEL_DEFAULT = 'Acknowledge:';

    const PARENT_KIND_MAP = {
        section: 'section',
        field: 'field',
        html: 'html',
        radio_option: 'radio_option',
    };

    function nodeKindValue(root) {
        const select = root.querySelector('[data-node-kind-select]');
        return select ? select.value : '';
    }

    function groupVisible(group, kind) {
        const allowed = FIELD_GROUPS[group];
        return allowed ? allowed.includes(kind) : false;
    }

    function updateParentOptions(root) {
        const select = root.querySelector('[data-parent-select], select[name="parent"]');
        const choicesByKind = window.CHECKLIST_PARENT_CHOICES;
        if (!select || !choicesByKind) return;

        const kind = nodeKindValue(root);
        const key = PARENT_KIND_MAP[kind] || 'section';
        const choices = choicesByKind[key] || [];
        const current = select.value;

        select.innerHTML = '';
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = kind === 'radio_option' ? '— Select radio group —' : '— Top level —';
        select.appendChild(empty);

        choices.forEach(function(item) {
            const opt = document.createElement('option');
            opt.value = String(item.id);
            opt.textContent = item.label;
            if (String(item.id) === current) {
                opt.selected = true;
            }
            select.appendChild(opt);
        });
    }

    function fieldTypeValue(root) {
        const select = root.querySelector('[data-field-type-select]');
        return select ? select.value : '';
    }

    function applyAcknowledgeLabelDefault(root) {
        if (fieldTypeValue(root) !== 'acknowledge') return;
        const en = root.querySelector('[name="label_en"]');
        const de = root.querySelector('[name="label_de"]');
        if (en && !String(en.value || '').trim()) en.value = ACKNOWLEDGE_LABEL_DEFAULT;
        if (de && !String(de.value || '').trim()) de.value = ACKNOWLEDGE_LABEL_DEFAULT;
    }

    function updateVisibility(root) {
        const kind = nodeKindValue(root);
        const fieldType = fieldTypeValue(root);
        root.querySelectorAll('[data-node-field-group]').forEach(function(el) {
            const group = el.getAttribute('data-node-field-group');
            var visible = groupVisible(group, kind);
            if (visible && FIELD_TYPE_GROUPS[group]) {
                visible = FIELD_TYPE_GROUPS[group].indexOf(fieldType) !== -1;
            }
            if (visible && group === 'field_advanced' && fieldType === 'acknowledge') {
                visible = false;
            }
            el.style.display = visible ? '' : 'none';
        });
        root.querySelectorAll('[data-label-caption]').forEach(function(el) {
            const sectionCaption = el.getAttribute('data-caption-section');
            const defaultCaption = el.getAttribute('data-caption-default');
            el.textContent = (kind === 'section' && sectionCaption) ? sectionCaption : defaultCaption;
        });
    }

    function refresh(root) {
        updateVisibility(root);
        updateParentOptions(root);
    }

    function initRoot(root) {
        const select = root.querySelector('[data-node-kind-select]');
        if (!select) return;
        const handler = function() { refresh(root); };
        select.addEventListener('change', handler);
        const fieldTypeSelect = root.querySelector('[data-field-type-select]');
        if (fieldTypeSelect) {
            fieldTypeSelect.addEventListener('change', function() {
                applyAcknowledgeLabelDefault(root);
                refresh(root);
            });
        }
        handler();
    }

    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('[data-checklist-node-form]').forEach(initRoot);
    });
})();