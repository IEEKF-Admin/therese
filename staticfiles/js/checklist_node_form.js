(function() {
    const FIELD_GROUPS = {
        field_type: ['field'],
        choice_key: ['radio_option'],
        label: ['section', 'field', 'html', 'radio_option'],
        content: ['html'],
        field_help: ['field'],
        required: ['field'],
        field_advanced: ['field'],
        visible_subject: ['field', 'html'],
        field_file: ['field'],
    };

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
        const select = root.querySelector('select[name="parent"]');
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

    function updateVisibility(root) {
        const kind = nodeKindValue(root);
        root.querySelectorAll('[data-node-field-group]').forEach(function(el) {
            const group = el.getAttribute('data-node-field-group');
            const visible = groupVisible(group, kind);
            el.style.display = visible ? '' : 'none';
            el.querySelectorAll('input, select, textarea').forEach(function(input) {
                input.disabled = !visible;
            });
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
        handler();
    }

    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('[data-checklist-node-form]').forEach(initRoot);
    });
})();