"""Reusable lifecycle for sample-wise evaluation."""

from __future__ import annotations

import os
from typing import Any, Optional

import numpy as np
import torch
from tqdm import tqdm

from ...util import util_data


class Evaluator:
    """Collect metadata, score every sample, summarize, and save the result."""

    def __init__(
        self,
        pred_dir_path: str,
        result_dir_path: str,
        gt_dir_path: Optional[str] = None,
        sort_result_by_metric: bool = True,
        device: torch.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        ),
    ) -> None:
        self.pred_dir_path: str = pred_dir_path
        self.gt_dir_path: Optional[str] = gt_dir_path
        self.result_dir_path: str = self.get_result_dir_path(result_dir_path)
        self.sort_result_by_metric: bool = sort_result_by_metric
        self.device: torch.device = device
        os.makedirs(self.result_dir_path, exist_ok=True)

    # Required subclass methods
    def get_meta_data_list(self, eval_dir: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_sample_wise_result(
        self,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    # Evaluation lifecycle
    def evaluate(self) -> None:
        eval_dir = self.get_eval_dir()
        metadata_list = self.get_meta_data_list(eval_dir)
        evaluation_results = self.get_result_dict(metadata_list)
        test_set_name = os.path.basename(os.path.normpath(eval_dir))
        self.save_result_dict(test_set_name, evaluation_results)

    def get_result_dict(
        self,
        metadata_list: list[dict[str, Any]],
    ) -> dict[str, Any]:
        evaluation_results = self.get_set_wise_result(metadata_list)
        self.prepare_for_scoring(metadata_list)

        sample_results: list[dict[str, Any]] = []
        for metadata in tqdm(metadata_list, desc="get result"):
            sample_results.append(self.get_sample_wise_result(metadata))

        if not sample_results:
            raise ValueError(
                "Evaluator produced no per-sample results "
                "(empty metadata_list?)"
            )

        evaluation_results["result_per_sample"] = sample_results
        evaluation_results["result"].update(
            self.summarize_scored_results(sample_results)
        )
        return evaluation_results

    def save_result_dict(
        self,
        test_set_name: str,
        result_dict: dict[str, Any],
    ) -> None:
        """Save one evaluated set. Subclasses may provide another format."""
        util_data.yaml_save(
            os.path.join(self.result_dir_path, f"{test_set_name}.yaml"),
            result_dict["result"],
        )
        if not self.sort_result_by_metric:
            return

        sample_results = result_dict["result_per_sample"]
        sortable_metric_names = [
            metric_name
            for metric_name in result_dict["result"]
            if all(metric_name in sample for sample in sample_results)
        ]
        for metric_name in sortable_metric_names:
            sorted_samples = util_data.sort_dict_list(
                dict_list=sample_results,
                key=metric_name,
            )
            util_data.yaml_save(
                os.path.join(
                    self.result_dir_path,
                    f"{test_set_name}_sort_by_{metric_name}.yaml",
                ),
                sorted_samples,
            )

    # Optional subclass hooks
    def get_result_dir_path(
        self,
        result_dir_path: str,
    ) -> str:
        prediction_dir_name = os.path.basename(
            os.path.normpath(self.pred_dir_path)
        )
        return os.path.join(result_dir_path, prediction_dir_name)

    def get_eval_dir(self) -> str:
        return self.pred_dir_path

    def get_set_wise_result(
        self,
        metadata_list: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return results that can be computed before sample-wise scoring."""
        return {"result": {}}

    def prepare_for_scoring(
        self,
        metadata_list: list[dict[str, Any]],
    ) -> None:
        """Prepare resources after metadata validation and before scoring."""
        pass

    def summarize_scored_results(
        self,
        sample_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return mean, median, and standard deviation for numeric results."""
        metric_names = sorted(
            name
            for name, value in sample_results[0].items()
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
        )
        return self.summarize_numeric_metrics(
            sample_results=sample_results,
            metric_names=metric_names,
        )

    # Statistic helper
    def summarize_numeric_metrics(
        self,
        sample_results: list[dict[str, Any]],
        metric_names: list[str],
    ) -> dict[str, dict[str, float]]:
        metric_values = {
            metric_name: [
                result[metric_name]
                for result in sample_results
            ]
            for metric_name in metric_names
        }
        return {
            metric_name: {
                "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "std": float(np.std(values)),
            }
            for metric_name, values in metric_values.items()
        }
