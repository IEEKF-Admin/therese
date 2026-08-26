(function() {
    function moveSelected(fromSelect, toSelect) {
        Array.prototype.slice.call(fromSelect.selectedOptions).forEach(function(opt) {
            toSelect.appendChild(opt);
            opt.selected = false;
        });
        sortOptions(toSelect);
    }

    function moveAll(fromSelect, toSelect) {
        Array.prototype.slice.call(fromSelect.options).forEach(function(opt) {
            toSelect.appendChild(opt);
            opt.selected = false;
        });
        sortOptions(toSelect);
    }

    function sortOptions(select) {
        var opts = Array.prototype.slice.call(select.options);
        opts.sort(function(a, b) {
            return a.textContent.localeCompare(b.textContent, undefined, { sensitivity: 'base' });
        });
        opts.forEach(function(opt) { select.appendChild(opt); });
    }

    function selectAllForSubmit(selectedSelect) {
        Array.prototype.forEach.call(selectedSelect.options, function(opt) {
            opt.selected = true;
        });
    }

    function initDualList(root) {
        if (root.dataset.dualListReady === '1') return;
        root.dataset.dualListReady = '1';

        var available = root.querySelector('.dual-list-available');
        var selected = root.querySelector('.dual-list-selected')
            || root.querySelector('.dual-list-panel:last-child select');
        if (!available || !selected) return;

        var addBtn = root.querySelector('.dual-list-add');
        var removeBtn = root.querySelector('.dual-list-remove');
        var addAllBtn = root.querySelector('.dual-list-add-all');
        var removeAllBtn = root.querySelector('.dual-list-remove-all');

        function syncSelected() { selectAllForSubmit(selected); }
        if (addBtn) addBtn.addEventListener('click', function() { moveSelected(available, selected); syncSelected(); });
        if (removeBtn) removeBtn.addEventListener('click', function() { moveSelected(selected, available); syncSelected(); });
        if (addAllBtn) addAllBtn.addEventListener('click', function() { moveAll(available, selected); syncSelected(); });
        if (removeAllBtn) removeAllBtn.addEventListener('click', function() { moveAll(selected, available); syncSelected(); });

        available.addEventListener('dblclick', function() { moveSelected(available, selected); syncSelected(); });
        selected.addEventListener('dblclick', function() { moveSelected(selected, available); syncSelected(); });
        syncSelected();

        var form = root.closest('form');
        if (form) {
            form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(function(btn) {
                btn.addEventListener('click', syncSelected);
            });
            form.addEventListener('submit', syncSelected);
        }
    }

    function initAll() {
        document.querySelectorAll('[data-dual-list]').forEach(initDualList);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
