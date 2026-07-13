(function() {
    function parseGermanDate(value) {
        if (!value) return null;
        const parts = value.trim().split('.');
        if (parts.length !== 3) return null;
        const day = parseInt(parts[0], 10);
        const month = parseInt(parts[1], 10);
        const year = parseInt(parts[2], 10);
        if (isNaN(day) || isNaN(month) || isNaN(year)) return null;
        return new Date(year, month - 1, day);
    }

    function contractDurationMonths(start, end) {
        if (!start || !end || end < start) return null;
        let months = (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth());
        if (end.getDate() >= start.getDate()) {
            months += 1;
        }
        return Math.max(months, 0);
    }

    function compareDuration(months, operator, threshold) {
        if (months === null || threshold === null || threshold === undefined || threshold === '') {
            return false;
        }
        const value = parseInt(threshold, 10);
        if (isNaN(value)) return false;
        if (operator === 'lt') return months < value;
        if (operator === 'lte') return months <= value;
        if (operator === 'gt') return months > value;
        if (operator === 'gte') return months >= value;
        if (operator === 'eq') return months === value;
        return false;
    }

    function evaluateVisibility(rule, months) {
        if (!rule) return true;
        if (rule.visibility_mode === 'never') return false;
        if (rule.visibility_mode === 'when_duration') {
            return compareDuration(
                months,
                rule.visibility_duration_operator,
                rule.visibility_duration_months,
            );
        }
        return true;
    }

    function evaluateRequired(rule, months, fieldKey, defaults) {
        if (!rule) {
            if (defaults && Object.prototype.hasOwnProperty.call(defaults, fieldKey)) {
                return defaults[fieldKey];
            }
            return false;
        }
        if (rule.required_mode === 'never') return false;
        if (rule.required_mode === 'when_duration') {
            if (!compareDuration(months, rule.required_duration_operator, rule.required_duration_months)) {
                return false;
            }
            return true;
        }
        if (rule.required_mode === 'always') return true;
        return false;
    }

    function getCurrentDurationMonths() {
        const startInput = document.querySelector('[data-contract-date][name="valid_from"], [name="valid_from"]');
        const endInput = document.querySelector('[data-contract-date][name="valid_until"], [name="valid_until"]');
        if (!startInput || !endInput) return null;
        const start = parseGermanDate(startInput.value);
        const end = parseGermanDate(endInput.value);
        return contractDurationMonths(start, end);
    }

    function getSelectedJobId() {
        const jobSelect = document.querySelector('[data-recruitment-job]');
        return jobSelect && jobSelect.value ? jobSelect.value : null;
    }

    function setFieldVisibility(fieldKey, visible) {
        document.querySelectorAll(`[data-recruitment-field="${fieldKey}"]`).forEach(function(wrapper) {
            wrapper.style.display = visible ? '' : 'none';
            wrapper.querySelectorAll('input, select, textarea').forEach(function(input) {
                if (!visible) {
                    input.removeAttribute('required');
                }
            });
        });
    }

    function setFieldRequired(fieldKey, required) {
        document.querySelectorAll(`[data-recruitment-field="${fieldKey}"]`).forEach(function(wrapper) {
            wrapper.querySelectorAll('input, select, textarea').forEach(function(input) {
                if (input.type === 'hidden' || input.type === 'checkbox') return;
                if (required) {
                    input.setAttribute('required', 'required');
                } else {
                    input.removeAttribute('required');
                }
            });
        });
        document.querySelectorAll(`[data-required-for="${fieldKey}"]`).forEach(function(marker) {
            marker.textContent = required ? '*' : '';
        });
        document.querySelectorAll(`label [data-required-label="${fieldKey}"]`).forEach(function(marker) {
            marker.textContent = required ? '*' : '';
        });
    }

    function applyJobFieldRules(config) {
        const jobId = getSelectedJobId();
        const months = getCurrentDurationMonths();
        const jobRules = jobId && config.jobRules[jobId] ? config.jobRules[jobId] : {};
        const defaults = config.defaultRequired || {};

        Object.keys(config.allFieldKeys || {}).forEach(function(fieldKey) {
            const rule = jobRules[fieldKey] || null;
            const visible = evaluateVisibility(rule, months);
            const required = visible && evaluateRequired(rule, months, fieldKey, defaults);
            setFieldVisibility(fieldKey, visible);
            setFieldRequired(fieldKey, required);
        });
    }

    function rebuildLimitationTemplateOptions(config) {
        const templateSelect = document.querySelector('[data-limitation-template]');
        if (!templateSelect) return;

        const jobId = getSelectedJobId();
        const currentValue = templateSelect.value;
        const textField = document.querySelector('[data-limitation-text]');

        templateSelect.innerHTML = '';
        const emptyOption = document.createElement('option');
        emptyOption.value = '';
        emptyOption.textContent = '-Empty-';
        templateSelect.appendChild(emptyOption);

        const reasons = (config.limitationReasons || []).filter(function(reason) {
            if (!jobId) return true;
            if (reason.applies_to_all_jobs) return true;
            return (reason.job_ids || []).map(String).includes(String(jobId));
        });

        reasons.forEach(function(reason) {
            const option = document.createElement('option');
            option.value = String(reason.id);
            option.textContent = reason.title;
            option.dataset.templateText = reason.text || '';
            templateSelect.appendChild(option);
        });

        if (currentValue && Array.from(templateSelect.options).some(function(opt) { return opt.value === currentValue; })) {
            templateSelect.value = currentValue;
        } else {
            templateSelect.value = '';
        }
    }

    function applyLimitationTemplate(config) {
        const templateSelect = document.querySelector('[data-limitation-template]');
        const textField = document.querySelector('[data-limitation-text]');
        if (!templateSelect || !textField) return;

        if (!templateSelect.value) {
            return;
        }

        const selected = templateSelect.options[templateSelect.selectedIndex];
        if (selected && selected.dataset.templateText !== undefined) {
            textField.value = selected.dataset.templateText;
        }
    }

    function formatEstimatedSalary(value) {
        if (value === null || value === undefined || value === '') {
            return '—';
        }
        const num = parseFloat(value);
        if (isNaN(num)) {
            return '—';
        }
        return num.toLocaleString('de-DE', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }) + ' €';
    }

    function updateEstimatedSalary(config) {
        const el = document.getElementById('estimated-salary-value');
        if (!el) {
            return;
        }
        const jobId = getSelectedJobId();
        if (!jobId || !config.jobPayscale) {
            el.textContent = '—';
            return;
        }
        const jobData = config.jobPayscale[jobId];
        if (!jobData) {
            el.textContent = '—';
            return;
        }
        if (
            config.payscaleData
            && jobData.pay_scale_group
            && jobData.experience_level !== null
            && jobData.experience_level !== undefined
        ) {
            const groupEntries = config.payscaleData[jobData.pay_scale_group];
            if (groupEntries) {
                const match = groupEntries.find(function(item) {
                    return item.experience_level === jobData.experience_level;
                });
                if (match) {
                    el.textContent = formatEstimatedSalary(match.monthly_salary);
                    return;
                }
            }
        }
        if (jobData.estimated_salary) {
            el.textContent = formatEstimatedSalary(jobData.estimated_salary);
            return;
        }
        el.textContent = '—';
    }

    window.initRecruitmentDynamicForm = function(config) {
        if (!config) return;

        function refresh() {
            if (config.enableJobRules) {
                applyJobFieldRules(config);
            }
            if (config.enableLimitationTemplates) {
                rebuildLimitationTemplateOptions(config);
            }
            updateEstimatedSalary(config);
        }

        document.addEventListener('change', function(event) {
            if (event.target.matches('[data-recruitment-job]')) {
                refresh();
            }
            if (event.target.matches('[data-contract-date], [name="valid_from"], [name="valid_until"]')) {
                if (config.enableJobRules) {
                    applyJobFieldRules(config);
                }
            }
            if (event.target.matches('[data-limitation-template]')) {
                applyLimitationTemplate(config);
            }
        });

        document.addEventListener('input', function(event) {
            if (event.target.matches('[data-contract-date], [name="valid_from"], [name="valid_until"]')) {
                if (config.enableJobRules) {
                    applyJobFieldRules(config);
                }
            }
        });

        refresh();
    };
})();