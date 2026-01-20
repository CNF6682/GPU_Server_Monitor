/**
 * Test script to inject mock GPU data for frontend verification.
 * 
 * Usage:
 * 1. Open the browser console (F12).
 * 2. Copy and paste the content of this file (excluding comments if you prefer).
 * 3. The server list or detail page will use the mock data on next refresh/load.
 */

(function () {
    if (typeof api === 'undefined') {
        console.error("API client not found. Make sure you are on index.html or server-detail.html");
        return;
    }

    console.log("Injecting Mock Data Interceptor...");

    const originalGetServers = api.getServers;

    // Override getServers to inject mock data
    api.getServers = async function () {
        console.log("Mock getServers called");
        const servers = await originalGetServers.call(this);

        // Inject mock data into the first server found
        if (servers && servers.length > 0) {
            const target = servers[0];
            target.name = "[Mock] " + target.name;

            // Mock 4 GPUs
            target.latest.gpu_count = 4;
            target.latest.gpus = [
                { index: 0, name: "NVIDIA A100-SXM4-40GB", util_pct: 85.5, mem_used_mb: 25000, mem_total_mb: 40960, temperature_c: 72 },
                { index: 1, name: "NVIDIA A100-SXM4-40GB", util_pct: 12.0, mem_used_mb: 1024, mem_total_mb: 40960, temperature_c: 45 },
                { index: 2, name: "NVIDIA A100-SXM4-40GB", util_pct: 98.2, mem_used_mb: 39000, mem_total_mb: 40960, temperature_c: 82 }, // High temp
                { index: 3, name: "NVIDIA A100-SXM4-40GB", util_pct: 0.0, mem_used_mb: 0, mem_total_mb: 40960, temperature_c: 38 }
            ];

            // Recalculate aggregates for consistency
            target.latest.gpu_util_pct = 85.5; // Max or Avg depending on backend logic, here simply setting a value

            console.log("Injected 4 Mock GPUs into server:", target.name);
        }

        return servers;
    };

    // Trigger a refresh if on overview page
    if (typeof loadServers === 'function') {
        loadServers();
    }
    // Trigger a refresh if on detail page
    if (typeof loadServerDetail === 'function') {
        loadServerDetail();
    }

    // Show toast
    if (typeof showToast === 'function') {
        showToast("已注入 Mock GPU 数据", "success");
    }
})();
