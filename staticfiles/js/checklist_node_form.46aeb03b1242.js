(function() {
    const FIELD_GROUPS = {
        field_type: ['field'],
        choice_key: ['radio_option'],
        label: ['section', 'field', 'html'],
        content: ['html'],
        field_help: ['field'],
        required: ['field'],
        field_advanced: ['field'],
        visible_subject: ['field', 'html'],
        field_file: ['field'],
    };

    function nodeKindValue(root) {
        const select = root.querySelector('[data-node-kind-select]');
        return select ? select.value : '';
    }

    function groupVisible(group, kind) {
        const allowed = FIELD_GROUPS[group];
        return allowed ? allowed.includes(kind) : false;
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

    function initRoot(root) {
        const select = root.querySelector('[data-node-kind-select]');
        if (!select) return;
        const handler = function() { updateVisibility(root); };
        select.addEventListener('change', handler);
        handler();
    }

    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('[data-checklist-node-form]').forEach(initRoot);
    });
})();
