"""
\u5355\u5143\u6d4b\u8bd5\uff1aGPU \u805a\u5408\u903b\u8f91

\u6d4b\u8bd5\u8986\u76d6\uff1a
- \u591a GPU \u60c5\u666f\uff1a\u6b63\u786e\u8ba1\u7b97 max/avg/sum
- \u5355 GPU \u60c5\u666f\uff1a\u805a\u5408\u503c\u7b49\u4e8e\u5355\u5361\u503c
- \u65e0 GPU \u60c5\u666f\uff1a\u6240\u6709\u503c\u4e3a None/0
- \u7f3a\u5931\u6570\u636e\uff1a\u5bb9\u9519\u5904\u7406
"""

import pytest
import sys
from pathlib import Path

# \u6dfb\u52a0\u9879\u76ee\u8def\u5f84\u5230 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor_aggregator.collector import aggregate_gpu_metrics


class TestAggreGPUMetrics:
    """GPU \u805a\u5408\u6307\u6807\u6d4b\u8bd5"""
    
    def test_multiple_gpus_normal(self):
        """\u6d4b\u8bd5\uff1a\u591a GPU \u6b63\u5e38\u573a\u666f"""
        gpus = [
            {"util_pct": 50.0, "mem_used_mb": 2048, "mem_total_mb": 8192},
            {"util_pct": 80.0, "mem_used_mb": 4096, "mem_total_mb": 8192},
            {"util_pct": 30.0, "mem_used_mb": 1024, "mem_total_mb": 8192}
        ]
        
        result = aggregate_gpu_metrics(gpus)
        
        assert result["gpu_count"] == 3
        assert result["gpu_util_pct"] == 80.0  # Max
        assert result["gpu_util_pct_avg"] == pytest.approx(53.33, rel=0.01)  # Avg
        assert result["gpu_mem_used_mb"] == 7168  # Sum: 2048 + 4096 + 1024
        assert result["gpu_mem_total_mb"] == 24576  # Sum: 3 * 8192
    
    def test_single_gpu(self):
        """\u6d4b\u8bd5\uff1a\u5355 GPU"""
        gpus = [
            {"util_pct": 65.5, "mem_used_mb": 3072, "mem_total_mb": 8192}
        ]
        
        result = aggregate_gpu_metrics(gpus)
        
        assert result["gpu_count"] == 1
        assert result["gpu_util_pct"] == 65.5  # Max equals single value
        assert result["gpu_util_pct_avg"] == 65.5  # Avg equals single value
        assert result["gpu_mem_used_mb"] == 3072
        assert result["gpu_mem_total_mb"] == 8192
    
    def test_no_gpus_none(self):
        """\u6d4b\u8bd5\uff1a\u65e0 GPU\uff08None\uff09"""
        result = aggregate_gpu_metrics(None)
        
        assert result["gpu_count"] == 0
        assert result["gpu_util_pct"] is None
        assert result["gpu_util_pct_avg"] is None
        assert result["gpu_mem_used_mb"] is None
        assert result["gpu_mem_total_mb"] is None
    
    def test_no_gpus_empty_list(self):
        """\u6d4b\u8bd5\uff1a\u65e0 GPU\uff08\u7a7a\u5217\u8868\uff09"""
        result = aggregate_gpu_metrics([])
        
        assert result["gpu_count"] == 0
        assert result["gpu_util_pct"] is None
        assert result["gpu_util_pct_avg"] is None
        assert result["gpu_mem_used_mb"] is None
        assert result["gpu_mem_total_mb"] is None
    
    def test_missing_util_pct(self):
        """\u6d4b\u8bd5\uff1a\u7f3a\u5931 util_pct \u5b57\u6bb5"""
        gpus = [
            {"util_pct": 50.0, "mem_used_mb": 2048, "mem_total_mb": 8192},
            {"mem_used_mb": 4096, "mem_total_mb": 8192},  # Missing util_pct
            {"util_pct": 30.0, "mem_used_mb": 1024, "mem_total_mb": 8192}
        ]
        
        result = aggregate_gpu_metrics(gpus)
        
        assert result["gpu_count"] == 3
        # \u5e94\u8be5\u53ea\u8ba1\u7b97\u6709\u503c\u7684 GPU
        assert result["gpu_util_pct"] == 50.0  # Max of [50, 30]
        assert result["gpu_util_pct_avg"] == 40.0  # Avg of [50, 30]
        # \u5185\u5b58\u805a\u5408\u5e94\u8be5\u5305\u62ec\u6240\u6709 GPU
        assert result["gpu_mem_used_mb"] == 7168
        assert result["gpu_mem_total_mb"] == 24576
    
    def test_missing_memory_fields(self):
        """\u6d4b\u8bd5\uff1a\u7f3a\u5931\u663e\u5b58\u5b57\u6bb5"""
        gpus = [
            {"util_pct": 50.0, "mem_used_mb": 2048, "mem_total_mb": 8192},
            {"util_pct": 80.0},  # Missing memory fields
            {"util_pct": 30.0, "mem_used_mb": 1024, "mem_total_mb": 8192}
        ]
        
        result = aggregate_gpu_metrics(gpus)
        
        assert result["gpu_count"] == 3
        assert result["gpu_util_pct"] == 80.0
        assert result["gpu_util_pct_avg"] == pytest.approx(53.33, rel=0.01)
        # \u663e\u5b58\u5e94\u8be5\u53ea\u7edf\u8ba1\u6709\u503c\u7684
        assert result["gpu_mem_used_mb"] == 3072  # Sum of [2048, 1024]
        assert result["gpu_mem_total_mb"] == 16384  # Sum of [8192, 8192]
    
    def test_all_fields_missing(self):
        """\u6d4b\u8bd5\uff1a\u6240\u6709 GPU \u6570\u636e\u90fd\u7f3a\u5931"""
        gpus = [
            {},  # Empty GPU info
            {}
        ]
        
        result = aggregate_gpu_metrics(gpus)
        
        assert result["gpu_count"] == 2  # Still counts GPU devices
        assert result["gpu_util_pct"] is None  # No valid utilization data
        assert result["gpu_util_pct_avg"] is None
        assert result["gpu_mem_used_mb"] is None
        assert result["gpu_mem_total_mb"] is None
    
    def test_heterogeneous_gpus(self):
        """\u6d4b\u8bd5\uff1a\u4e0d\u540c\u578b\u53f7\u7684 GPU\uff08\u4e0d\u540c\u663e\u5b58\u5927\u5c0f\uff09"""
        gpus = [
            {"util_pct": 45.0, "mem_used_mb": 3000, "mem_total_mb": 12288},  # 12GB
            {"util_pct": 90.0, "mem_used_mb": 6000, "mem_total_mb": 8192},   # 8GB
            {"util_pct": 20.0, "mem_used_mb": 16000, "mem_total_mb": 40960}  # 40GB
        ]
        
        result = aggregate_gpu_metrics(gpus)
        
        assert result["gpu_count"] == 3
        assert result["gpu_util_pct"] == 90.0  # Max
        assert result["gpu_util_pct_avg"] == pytest.approx(51.67, rel=0.01)  # Avg
        assert result["gpu_mem_used_mb"] == 25000  # Sum
        assert result["gpu_mem_total_mb"] == 61440  # Sum: 12288 + 8192 + 40960
    
    def test_zero_utilization(self):
        """\u6d4b\u8bd5\uff1a\u5168\u90e8 GPU \u5229\u7528\u7387\u4e3a 0"""
        gpus = [
            {"util_pct": 0.0, "mem_used_mb": 0, "mem_total_mb": 8192},
            {"util_pct": 0.0, "mem_used_mb": 0, "mem_total_mb": 8192}
        ]
        
        result = aggregate_gpu_metrics(gpus)
        
        assert result["gpu_count"] == 2
        assert result["gpu_util_pct"] == 0.0
        assert result["gpu_util_pct_avg"] == 0.0
        assert result["gpu_mem_used_mb"] == 0
        assert result["gpu_mem_total_mb"] == 16384
    
    def test_full_utilization(self):
        """\u6d4b\u8bd5\uff1a\u5168\u90e8 GPU \u6ee1\u8f7d"""
        gpus = [
            {"util_pct": 100.0, "mem_used_mb": 8192, "mem_total_mb": 8192},
            {"util_pct": 100.0, "mem_used_mb": 8192, "mem_total_mb": 8192}
        ]
        
        result = aggregate_gpu_metrics(gpus)
        
        assert result["gpu_count"] == 2
        assert result["gpu_util_pct"] == 100.0
        assert result["gpu_util_pct_avg"] == 100.0
        assert result["gpu_mem_used_mb"] == 16384
        assert result["gpu_mem_total_mb"] == 16384
    
    def test_with_optional_fields(self):
        """\u6d4b\u8bd5\uff1a\u5e26\u6709\u53ef\u9009\u5b57\u6bb5\uff08name, temperature\uff09"""
        gpus = [
            {
                "index": 0,
                "name": "NVIDIA A100",
                "util_pct": 60.0,
                "mem_used_mb": 16384,
                "mem_total_mb": 40960,
                "temperature_c": 75.0
            },
            {
                "index": 1,
                "name": "NVIDIA A100",
                "util_pct": 40.0,
                "mem_used_mb": 8192,
                "mem_total_mb": 40960,
                "temperature_c": 68.0
            }
        ]
        
        result = aggregate_gpu_metrics(gpus)
        
        # \u805a\u5408\u903b\u8f91\u4e0d\u5e94\u53d7\u53ef\u9009\u5b57\u6bb5\u5f71\u54cd
        assert result["gpu_count"] == 2
        assert result["gpu_util_pct"] == 60.0
        assert result["gpu_util_pct_avg"] == 50.0
        assert result["gpu_mem_used_mb"] == 24576
        assert result["gpu_mem_total_mb"] == 81920


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
