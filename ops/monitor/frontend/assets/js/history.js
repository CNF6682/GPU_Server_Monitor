/**
 * 历史页逻辑
 *
 * 查询并展示按小时聚合的历史数据（samples_hourly）。
 */

const state = {
    servers: [],
    limit: 20,
    offset: 0,
    total: 0,
    loading: false,
};

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function toIsoNoMs(date) {
    return date.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

function datetimeLocalToIsoNoMs(value) {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return toIsoNoMs(date);
}

function setDatetimeLocalValue(input, date) {
    const pad = (n) => String(n).padStart(2, '0');
    const yyyy = date.getFullYear();
    const mm = pad(date.getMonth() + 1);
    const dd = pad(date.getDate());
    const hh = pad(date.getHours());
    const mi = pad(date.getMinutes());
    input.value = `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

function getSelectedServerIds() {
    const select = document.getElementById('server-filter');
    const ids = Array.from(select.selectedOptions).map((opt) => opt.value).filter(Boolean);
    return ids;
}

function buildQueryParams({ exportMode = false } = {}) {
    const serverIds = getSelectedServerIds();
    const fromInput = document.getElementById('from-input').value;
    const toInput = document.getElementById('to-input').value;
    const sortBy = document.getElementById('sort-by').value;
    const sortOrder = document.getElementById('sort-order').value;

    const params = new URLSearchParams();

    if (serverIds.length > 0) params.set('server_ids', serverIds.join(','));

    const fromIso = datetimeLocalToIsoNoMs(fromInput);
    const toIso = datetimeLocalToIsoNoMs(toInput);
    if (fromIso) params.set('from', fromIso);
    if (toIso) params.set('to', toIso);

    if (sortBy) params.set('sort_by', sortBy);
    if (sortOrder) params.set('sort_order', sortOrder);

    if (!exportMode) {
        params.set('limit', String(state.limit));
        params.set('offset', String(state.offset));
    }

    return params;
}

async function loadServersForFilter() {
    const servers = await api.getServers();
    state.servers = servers || [];

    const select = document.getElementById('server-filter');
    select.innerHTML = state.servers
        .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
        .join('');
}

function renderRows(rows) {
    const tbody = document.getElementById('history-tbody');

    if (!rows || rows.length === 0) {
        tbody.innerHTML = `
      <tr>
        <td colspan="8" class="text-center py-4 text-muted">暂无数据</td>
      </tr>
    `;
        return;
    }

    tbody.innerHTML = rows
        .map((r) => {
            const diskText = r.disk_total_bytes
                ? `${formatPercent(r.disk_used_pct)} (${formatBytes(r.disk_used_bytes)} / ${formatBytes(r.disk_total_bytes)})`
                : '-';
            const gpuMemText = r.gpu_mem_total_mb
                ? `${r.gpu_mem_used_mb ?? '-'} / ${r.gpu_mem_total_mb} MB`
                : '-';

            return `
        <tr>
          <td class="text-muted">${formatTime(r.ts)}</td>
          <td>${escapeHtml(r.server_name || String(r.server_id))}</td>
          <td>${formatPercent(r.cpu_pct_avg)}</td>
          <td>${formatPercent(r.cpu_pct_max)}</td>
          <td>${diskText}</td>
          <td>${formatPercent(r.gpu_util_pct_avg)}</td>
          <td>${formatPercent(r.gpu_util_pct_max)}</td>
          <td>${gpuMemText}</td>
        </tr>
      `;
        })
        .join('');
}

function updatePagination() {
    const summary = document.getElementById('pagination-summary');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');

    const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
    const currentPage = Math.floor(state.offset / state.limit) + 1;

    summary.textContent = `共 ${state.total} 条，当前第 ${currentPage}/${totalPages} 页（每页 ${state.limit} 条）`;

    prevBtn.disabled = state.offset <= 0 || state.loading;
    nextBtn.disabled = state.offset + state.limit >= state.total || state.loading;
}

async function loadHistory() {
    state.loading = true;
    updatePagination();

    try {
        const params = buildQueryParams();
        const res = await api.getHourlyHistory(params);
        state.total = res.total || 0;
        renderRows(res.data || []);
    } catch (error) {
        console.error('Failed to load history:', error);
        showToast(`加载失败: ${error.message}`, 'danger');
        renderRows([]);
        state.total = 0;
    } finally {
        state.loading = false;
        updatePagination();
    }
}

function applyFilters() {
    state.offset = 0;
    loadHistory();
}

function resetFilters() {
    const serverSelect = document.getElementById('server-filter');
    Array.from(serverSelect.options).forEach((opt) => (opt.selected = false));

    document.getElementById('sort-by').value = 'ts';
    document.getElementById('sort-order').value = 'desc';

    setQuickRangeHours(24);
    applyFilters();
}

function setQuickRangeHours(hours) {
    const now = new Date();
    const from = new Date(now.getTime() - hours * 3600 * 1000);
    setDatetimeLocalValue(document.getElementById('from-input'), from);
    setDatetimeLocalValue(document.getElementById('to-input'), now);
}

function clearRange() {
    document.getElementById('from-input').value = '';
    document.getElementById('to-input').value = '';
}

function goPrev() {
    if (state.offset <= 0) return;
    state.offset = Math.max(0, state.offset - state.limit);
    loadHistory();
}

function goNext() {
    if (state.offset + state.limit >= state.total) return;
    state.offset += state.limit;
    loadHistory();
}

function exportCsv() {
    const params = buildQueryParams({ exportMode: true });
    const url = `${API_BASE}/api/history/hourly/export?${params.toString()}`;
    window.location.href = url;
}

async function init() {
    try {
        await loadServersForFilter();
        resetFilters();
    } catch (error) {
        console.error('Failed to init history page:', error);
        showToast(`初始化失败: ${error.message}`, 'danger');
        renderRows([]);
        state.total = 0;
        updatePagination();
    }
}

document.addEventListener('DOMContentLoaded', init);
