"""
独立的 GPU 聚合逻辑测试（无依赖）

包含 aggregate_gpu_metrics 函数的副本以便独立测试。
"""

from typing import Optional, Dict, Any


def aggregate_gpu_metrics(gpus: Optional[list]) -> Dict[str, Any]:
    """
    聚合多 GPU 指标，生成兼容字段
    
    Args:
        gpus: GPU 数组（来自 Agent 的 gpus 字段）
    
    Returns:
        包含聚合指标的字典：
        - gpu_count: GPU 数量
        - gpu_util_pct: 最高利用率（最忙的 GPU）
        - gpu_util_pct_avg: 平均利用率
        - gpu_mem_used_mb: 总显存使用（所有 GPU 之和）
        - gpu_mem_total_mb: 总显存容量（所有 GPU 之和）
    """
    if not gpus:
        return {
            "gpu_count": 0,
            "gpu_util_pct": None,
            "gpu_util_pct_avg": None,
            "gpu_mem_used_mb": None,
            "gpu_mem_total_mb": None,
        }
    
    # 提取利用率列表（容错：跳过缺失数据）
    util_values = [g.get("util_pct") for g in gpus if g.get("util_pct") is not None]
    mem_used_values = [g.get("mem_used_mb") for g in gpus if g.get("mem_used_mb") is not None]
    mem_total_values = [g.get("mem_total_mb") for g in gpus if g.get("mem_total_mb") is not None]
    
    return {
        "gpu_count": len(gpus),
        "gpu_util_pct": max(util_values) if util_values else None,  # 最忙的 GPU
        "gpu_util_pct_avg": sum(util_values) / len(util_values) if util_values else None,
        "gpu_mem_used_mb": sum(mem_used_values) if mem_used_values else None,
        "gpu_mem_total_mb": sum(mem_total_values) if mem_total_values else None,
    }


def assert_approx_equal(a, b, rel=0.01):
    """检查两个浮点数是否近似相等"""
    if abs(a - b) / max(abs(a), abs(b), 1) > rel:
        raise AssertionError(f"{a} != {b} (within {rel*100}%)")


def test_multiple_gpus_normal():
    """测试：多 GPU 正常场景"""
    print("Testing: Multiple GPUs (normal case)...")
    gpus = [
        {"util_pct": 50.0, "mem_used_mb": 2048, "mem_total_mb": 8192},
        {"util_pct": 80.0, "mem_used_mb": 4096, "mem_total_mb": 8192},
        {"util_pct": 30.0, "mem_used_mb": 1024, "mem_total_mb": 8192}
    ]
    
    result = aggregate_gpu_metrics(gpus)
    
    assert result["gpu_count"] == 3, f"Expected 3 GPUs, got {result['gpu_count']}"
    assert result["gpu_util_pct"] == 80.0, f"Expected max 80.0, got {result['gpu_util_pct']}"
    assert_approx_equal(result["gpu_util_pct_avg"], 53.33, rel=0.01)
    assert result["gpu_mem_used_mb"] == 7168, f"Expected 7168, got {result['gpu_mem_used_mb']}"
    assert result["gpu_mem_total_mb"] == 24576, f"Expected 24576, got {result['gpu_mem_total_mb']}"
    print("  [PASSED]")


def test_single_gpu():
    """测试：单 GPU"""
    print("Testing: Single GPU...")
    gpus = [
        {"util_pct": 65.5, "mem_used_mb": 3072, "mem_total_mb": 8192}
    ]
    
    result = aggregate_gpu_metrics(gpus)
    
    assert result["gpu_count"] == 1
    assert result["gpu_util_pct"] == 65.5
    assert result["gpu_util_pct_avg"] == 65.5
    assert result["gpu_mem_used_mb"] == 3072
    assert result["gpu_mem_total_mb"] == 8192
    print("  [PASSED]")


def test_no_gpus_none():
    """测试：无 GPU (None)"""
    print("Testing: No GPUs (None)...")
    result = aggregate_gpu_metrics(None)
    
    assert result["gpu_count"] == 0
    assert result["gpu_util_pct"] is None
    assert result["gpu_util_pct_avg"] is None
    assert result["gpu_mem_used_mb"] is None
    assert result["gpu_mem_total_mb"] is None
    print("  [PASSED]")


def test_no_gpus_empty_list():
    """测试：无 GPU (空列表)"""
    print("Testing: No GPUs (empty list)...")
    result = aggregate_gpu_metrics([])
    
    assert result["gpu_count"] == 0
    assert result["gpu_util_pct"] is None
    assert result["gpu_util_pct_avg"] is None
    assert result["gpu_mem_used_mb"] is None
    assert result["gpu_mem_total_mb"] is None
    print("  [PASSED]")


def test_missing_util_pct():
    """测试：缺失 util_pct 字段"""
    print("Testing: Missing util_pct...")
    gpus = [
        {"util_pct": 50.0, "mem_used_mb": 2048, "mem_total_mb": 8192},
        {"mem_used_mb": 4096, "mem_total_mb": 8192},  # Missing util_pct
        {"util_pct": 30.0, "mem_used_mb": 1024, "mem_total_mb": 8192}
    ]
    
    result = aggregate_gpu_metrics(gpus)
    
    assert result["gpu_count"] == 3
    assert result["gpu_util_pct"] == 50.0
    assert result["gpu_util_pct_avg"] == 40.0
    assert result["gpu_mem_used_mb"] == 7168
    assert result["gpu_mem_total_mb"] == 24576
    print("  [PASSED]")


def test_heterogeneous_gpus():
    """测试：不同型号的 GPU（不同显存大小）"""
    print("Testing: Heterogeneous GPUs...")
    gpus = [
        {"util_pct": 45.0, "mem_used_mb": 3000, "mem_total_mb": 12288},
        {"util_pct": 90.0, "mem_used_mb": 6000, "mem_total_mb": 8192},
        {"util_pct": 20.0, "mem_used_mb": 16000, "mem_total_mb": 40960}
    ]
    
    result = aggregate_gpu_metrics(gpus)
    
    assert result["gpu_count"] == 3
    assert result["gpu_util_pct"] == 90.0
    assert_approx_equal(result["gpu_util_pct_avg"], 51.67, rel=0.01)
    assert result["gpu_mem_used_mb"] == 25000
    assert result["gpu_mem_total_mb"] == 61440
    print("  [PASSED]")


def test_zero_utilization():
    """测试：全部 GPU 利用率为 0"""
    print("Testing: Zero utilization...")
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
    print("  [PASSED]")


def test_full_utilization():
    """测试：全部 GPU 满载"""
    print("Testing: Full utilization...")
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
    print("  [PASSED]")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("GPU Aggregation Logic Tests (Standalone)")
    print("=" * 60)
    print()
    
    tests = [
        test_multiple_gpus_normal,
        test_single_gpu,
        test_no_gpus_none,
        test_no_gpus_empty_list,
        test_missing_util_pct,
        test_heterogeneous_gpus,
        test_zero_utilization,
        test_full_utilization,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAILED]: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR]: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)
    
    if failed == 0:
        print("\n[OK] All tests passed!")
        print("\nThe GPU aggregation logic correctly handles:")
        print("  * Multiple GPUs with max/avg/sum aggregation")
        print("  * Single GPU scenarios")
        print("  * No GPU scenarios (None and empty list)")
        print("  * Missing data fields (graceful degradation)")
        print("  * Heterogeneous GPU configurations")
        print("  * Edge cases (zero and full utilization)")
        return 0
    else:
        print(f"\n[FAIL] {failed} test(s) failed!")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
