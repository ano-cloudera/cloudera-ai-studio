from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml


def _normalize(value: str) -> str:
    return re.sub(r"[\s_\-.,!?;:'\"/]+", "", value).casefold()


# Words that carry no metric-identifying meaning on their own (Indonesian and
# English function words, plus generic question phrasing) - excluded from
# token-overlap matching in resolve_metric so a short/common word like
# "nilai" or "value" doesn't dominate the score or cause spurious partial
# matches across unrelated metrics.
_STOPWORDS = frozenset({
    "yang", "dengan", "dan", "atau", "untuk", "dari", "pada", "ini", "itu",
    "mana", "apa", "apakah", "bagaimana", "berapa", "adalah", "the", "a",
    "an", "of", "for", "with", "and", "or", "is", "are", "value", "nilai",
    "per", "each", "setiap", "total", "jumlah",
})


def _tokenize(value: str) -> set[str]:
    """Splits into lowercase word tokens (letters/digits only, "sell-in"
    becomes ["sell", "in"]) and drops stopwords - used for word-overlap
    matching, distinct from _normalize's whitespace-stripped exact-substring
    form. A phrase like "nilai Sell-In terbesar" and a synonym like
    "material sell-in value" share {"sell", "in"} either way, but
    tokenization also lets each individual content word be checked for
    membership regardless of the words around it."""
    return {word for word in re.findall(r"[a-z0-9]+", value.casefold()) if word and word not in _STOPWORDS}


# Registry-staged semantic models (banking demo, user-authored OSSIE): keep
# "total"/"jumlah" for matching "total amount" style questions.
_CATALOG_STOPWORDS = _STOPWORDS - frozenset({"total", "jumlah"})


def _catalog_tokenize(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", value.casefold()) if word and word not in _CATALOG_STOPWORDS}


def _is_semantic_registry_catalog(metrics: dict[str, Any]) -> bool:
    if not metrics:
        return False
    for key in metrics:
        lowered = key.casefold()
        if lowered.startswith("sat_") or "sell_in" in lowered or "sell_out" in lowered or lowered.startswith("gross_"):
            return False
    return True


class TempoOssieRegistry:
    """Read-only registry for the official-root Apache Ossie model."""

    def __init__(self, project_dir: Path, *, validate_profile: bool = True):
        self.project_dir = project_dir.resolve()
        self.model_path = self.project_dir / "ossie" / "tempo_core.ossie.yaml"
        self.governance_path = self.project_dir / "ossie" / "tempo_governance.yaml"
        self.golden_path = self.project_dir / "ossie" / "golden_questions.yaml"

        self.model = self._load(self.model_path)
        self.governance = self._load(self.governance_path)
        self.golden_questions = self._load(self.golden_path)
        self.datasets = {item["name"]: item for item in self.model.get("datasets", [])}
        self.metrics = {item["name"]: item for item in self.model.get("metrics", [])}
        self.dataset_fields = {
            name: {field["name"]: field for field in dataset.get("fields", [])}
            for name, dataset in self.datasets.items()
        }
        self.metric_configs = {
            name: self.tempo_extension(metric) for name, metric in self.metrics.items()
        }
        from app.semantic.runtime_extensions import (
            apply_runtime_extensions,
            resolve_runtime_extensions,
        )

        self.runtime_extensions = resolve_runtime_extensions(self.governance, self.datasets)
        if self.runtime_extensions:
            apply_runtime_extensions(
                self.runtime_extensions,
                datasets=self.datasets,
                metrics=self.metrics,
                dataset_fields=self.dataset_fields,
            )
        else:
            self.runtime_extensions = None
        for name, metric in self.metrics.items():
            if name not in self.metric_configs:
                self.metric_configs[name] = self.tempo_extension(metric)
        if validate_profile:
            self.validate()
        else:
            self._validate_minimal()

    def _validate_minimal(self) -> None:
        errors: list[str] = []
        if not self.datasets:
            errors.append("No datasets in OSSIE artifact")
        if not self.metrics:
            errors.append("No metrics in OSSIE artifact")
        if errors:
            raise ValueError("Invalid OSSIE registry:\n- " + "\n- ".join(errors))

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"Expected YAML object in {path}")
        return value

    @staticmethod
    def tempo_extension(item: dict[str, Any]) -> dict[str, Any]:
        for extension in item.get("custom_extensions", []):
            if extension.get("vendor_name") != "TEMPO":
                continue
            data = extension.get("data", {})
            return json.loads(data) if isinstance(data, str) else dict(data)
        return {}

    @staticmethod
    def ansi_expression(item: dict[str, Any]) -> str:
        expression = item.get("expression", {})
        if isinstance(expression, str):
            return expression
        for candidate in expression.get("dialects", []):
            if candidate.get("dialect") == "ANSI_SQL":
                return str(candidate["expression"])
        raise ValueError(f"No ANSI_SQL expression for {item.get('name')}")

    def validate(self) -> None:
        errors: list[str] = []
        if self.model.get("name") != "tempo_q4_governed":
            errors.append("Unexpected Ossie model name")
        # Minimums, not exact counts: the original Semantic Contract v1 (5
        # datasets / 28 metrics) is the floor. The 24 Sep 2026 journey
        # expansion (Stock Tempo -> Sales -> B2B -> SAT-IDM -> OOS, see
        # TEMPO_DATAMART_PLAN.md §8.1) added 9 more datasets and 13 more
        # metrics on top of that floor - an exact-count check would reject
        # any further intentional growth of the governed model.
        if len(self.datasets) < 5:
            errors.append("TEMPO Impala profile expects at least five datasets")
        if len(self.metrics) < 28:
            errors.append("TEMPO Impala profile expects at least 28 metrics")
        if self.model.get("relationships"):
            errors.append("Runtime joins are disabled for Semantic Contract v1")

        for dataset_name, dataset in self.datasets.items():
            fields = self.dataset_fields[dataset_name]
            for key in dataset.get("primary_key", []):
                if key not in fields:
                    errors.append(f"{dataset_name} primary key references unknown field {key}")

        metric_ids: set[str] = set()
        for metric_name, metric in self.metrics.items():
            config = self.metric_configs[metric_name]
            metric_id = config.get("metric_id")
            dataset_name = config.get("base_dataset")
            if not metric_id:
                errors.append(f"{metric_name} has no metric_id")
            elif metric_id in metric_ids:
                errors.append(f"Duplicate metric_id {metric_id}")
            metric_ids.add(str(metric_id))
            if dataset_name not in self.datasets:
                errors.append(f"{metric_name} has invalid base_dataset {dataset_name}")
                continue
            dimensions = {
                name
                for name, field in self.dataset_fields[dataset_name].items()
                if "dimension" in field
            }
            unknown = set(config.get("allowed_dimensions", [])) - dimensions
            if unknown:
                errors.append(f"{metric_name} has unknown dimensions {sorted(unknown)}")

        if errors:
            raise ValueError("Invalid TEMPO Ossie registry:\n- " + "\n- ".join(errors))

    def metric_aliases(self, metric_name: str) -> list[str]:
        from app.semantic.runtime_extensions import display_name_for_metric

        metric = self.metrics[metric_name]
        context = metric.get("ai_context", {})
        values = [metric_name, metric_name.replace("_", " "), metric.get("description", "")]
        display = display_name_for_metric(metric_name, self.runtime_extensions)
        if display:
            values.append(display)
        if isinstance(context, dict):
            if context.get("display_name"):
                values.append(str(context["display_name"]))
            values.extend(context.get("synonyms", []))
        return [str(value) for value in values if value]

    def _metric_picker_clarification(self, question: str) -> dict[str, Any]:
        from app.ask_data.metric_labels import humanize_metric_label

        normalized = _normalize(question)
        scored: list[tuple[int, str]] = []
        for metric_name in self.metrics:
            definition = self.metric_definition(metric_name)
            score = 0
            label_blob = " ".join(self.metric_aliases(metric_name)).casefold()
            for tok in _catalog_tokenize(question):
                if len(tok) >= 4 and tok in label_blob:
                    score += 40
            for alias in self.metric_aliases(metric_name):
                if _normalize(alias) in normalized:
                    score += 100
            entity_hints: set[str] = set()
            if any(term in normalized for term in ("customer", "nasabah", "pelanggan")):
                entity_hints.add("customers")
            if any(term in normalized for term in ("transaction", "transaksi")):
                entity_hints.add("transactions")
            dataset_name = str(self.metric_configs.get(metric_name, {}).get("base_dataset") or "")
            if entity_hints and dataset_name in entity_hints:
                score += 80
            if score <= 0:
                score = 1
            scored.append((score, metric_name))
        scored.sort(reverse=True)
        top = scored[:4]
        options: list[dict[str, str]] = []
        for _, metric_name in top:
            definition = self.metric_definition(metric_name)
            label = humanize_metric_label(name=metric_name, definition=definition)
            options.append({"type": "semantic_metric", "id": metric_name, "name": label})
        return {
            "status": "needs_clarification",
            "reason": "metric_ambiguous",
            "question": self.governance.get(
                "unknown_metric_question",
                "Metrik mana yang ingin Anda lihat? Pilih salah satu metric yang terdaftar di semantic layer.",
            ),
            "options": options,
        }

    def _resolve_semantic_registry_catalog_metric(self, question: str) -> dict[str, Any]:
        normalized = _normalize(question)
        question_tokens = _catalog_tokenize(question)
        entity_hints: set[str] = set()
        if any(term in normalized for term in ("customer", "customers", "nasabah", "pelanggan")):
            entity_hints.add("customers")
        if any(term in normalized for term in ("transaction", "transactions", "transaksi", "payment", "pembayaran")):
            entity_hints.add("transactions")

        has_amount_intent = any(
            term in normalized for term in ("amount", "nominal", "nilai transaksi", "monetary", "revenue")
        )
        wants_total_tx_amount = (
            "totaltransactionamount" in normalized
            or (
                "total" in normalized
                and ("transaction" in normalized or "transaksi" in normalized)
                and has_amount_intent
            )
        )
        has_channel_intent = any(
            term in normalized for term in ("channel", "saluran", "kanal")
        )
        wants_channel_rank = has_channel_intent and any(
            term in normalized
            for term in ("highest", "largest", "top", "terbesar", "tertinggi", "paling")
        )

        candidates: list[tuple[int, str, str]] = []
        for metric_name in self.metrics:
            config = self.metric_configs.get(metric_name, {})
            dataset_name = str(config.get("base_dataset") or "")
            score = 0
            matched_alias = metric_name
            mn_cf = metric_name.casefold()
            expr_cf = str(config.get("expression") or "").casefold().replace(" ", "")
            for alias in self.metric_aliases(metric_name):
                normalized_alias = _normalize(alias)
                alias_tokens = _catalog_tokenize(alias)
                if normalized_alias and normalized_alias in normalized:
                    score = max(score, 200 + len(normalized_alias))
                    matched_alias = alias
                elif alias_tokens and alias_tokens <= question_tokens:
                    score = max(score, 120 + len(alias_tokens))
                    matched_alias = alias
                elif len(alias_tokens) == 1 and alias_tokens <= question_tokens:
                    token = next(iter(alias_tokens))
                    if len(token) >= 4:
                        score = max(score, 80 + len(token))
                        matched_alias = alias
            if entity_hints and dataset_name in entity_hints:
                score += 150
            if has_amount_intent:
                if "amount" in mn_cf or "sum(amount" in expr_cf:
                    score += 220
                if "customer_id" in mn_cf and "amount" not in mn_cf:
                    score -= 200
            if wants_total_tx_amount and ("amount" in mn_cf or metric_name == "total_amount"):
                score += 280
            if has_channel_intent:
                if "amount" in mn_cf or "sum(amount" in expr_cf:
                    score += 180
                if "customer_id" in mn_cf and "amount" not in mn_cf:
                    score -= 220
            if wants_channel_rank and ("amount" in mn_cf or "sum(amount" in expr_cf):
                score += 240
            if "amount" in normalized and "amount" in mn_cf:
                score += 60
            if any(t in normalized for t in ("trend", "pertumbuhan", "per bulan", "bulanan", "monthly", "time series")):
                if "transaction" in metric_name.casefold():
                    score += 90
                if "transaction_id" in metric_name.casefold():
                    score += 40
            if any(t in normalized for t in ("jumlah transaksi", "banyak transaksi", "count transaksi")):
                if "transaction_id" in metric_name.casefold():
                    score += 120
                if "amount" in metric_name.casefold():
                    score -= 40
            from app.semantic.runtime_extensions import metric_resolver_score_bonus

            score += metric_resolver_score_bonus(normalized, metric_name, self.runtime_extensions)
            if score > 0:
                candidates.append((score, metric_name, matched_alias))

        if not candidates:
            return self._metric_picker_clarification(question)

        candidates.sort(reverse=True)
        top_score, metric_name, alias = candidates[0]
        runner_up = candidates[1][0] if len(candidates) > 1 else 0
        wants_tx_count = entity_hints == {"transactions"} and any(
            t in normalized
            for t in (
                "jumlah transaksi",
                "banyak transaksi",
                "count transaksi",
                "trend",
                "pertumbuhan",
                "per bulan",
                "bulanan",
                "12 bulan",
            )
        )
        if wants_tx_count:
            tx_count = next(
                (item for item in candidates if "transaction_id" in item[1].casefold()),
                None,
            )
            if tx_count is not None:
                _, metric_name, alias = tx_count
                return {
                    "status": "resolved",
                    "metric": metric_name,
                    "matched_alias": alias,
                    "definition": self.metric_definition(metric_name),
                    "dimension_mismatch": [],
                }
        if len(candidates) > 1 and top_score - runner_up < 25:
            return self._metric_picker_clarification(question)

        return {
            "status": "resolved",
            "metric": metric_name,
            "matched_alias": alias,
            "definition": self.metric_definition(metric_name),
            "dimension_mismatch": [],
        }

    def resolve_ambiguity(self, question: str) -> dict[str, Any] | None:
        normalized = _normalize(question)
        words = set(re.findall(r"[a-z0-9]+", question.casefold()))

        # SAT Promo currently covers December 2024 field-audit observations
        # only. The source has no promo cost or causal revenue attribution.
        # Stop those requests before generic Sales ambiguity can redirect a
        # promo ROI/revenue question to Sell-In.
        #
        # Tempo confirmed on 28 Sep 2026 (Pak Hieronimus Gunawan, WhatsApp,
        # replying to "Y = active kah?" with "abaikan saja pak, di list
        # tersebut, artinya aktif") that every row in this data represents
        # an active promo observation - program_status codes Y/X/T do not
        # distinguish active from inactive. This means a plain "promo
        # aktif" question is now answerable (the whole dataset is active,
        # see promo_observation_count/promo_material_count's ai_context),
        # so it is intentionally NOT in the blocklist below anymore. A
        # request that still implies an active/inactive SPLIT by status
        # (mixed_status_meaning below) remains blocked, since that
        # distinction was never confirmed - only "all active" was.
        mentions_promo = "promo" in normalized
        requests_mixed_status_meaning = any(
            term in normalized
            for term in ("promotidakaktif", "promononaktif", "promoinaktif")
        )
        requests_promo_attribution = any(
            term in normalized
            for term in (
                "roi",
                "revenue",
                "pendapatan",
                "uplift",
                "efektivitas",
                "effectivepromo",
            )
        )
        requests_unavailable_promo_period = any(
            term in normalized
            for term in ("oktober", "november", "q4", "kuartal4")
        )
        if mentions_promo and requests_mixed_status_meaning:
            return {
                "status": "unsupported",
                "reason": "promo_business_definition_unavailable",
                "question": (
                    "SAT Promo hanya mendukung observasi audit Desember 2024. "
                    "Seluruh data ini adalah observasi promo aktif (dikonfirmasi "
                    "Tempo); kode status Y/X/T tidak membedakan aktif/tidak aktif, "
                    "jadi tidak bisa memilah subset yang tidak aktif."
                ),
                "suggested_questions": [
                    "Jumlah observasi promo per mekanisme Desember 2024",
                    "Berapa jumlah material yang tercakup SAT Promo Desember 2024?",
                    "Bagaimana distribusi kode program status Y/X/T?",
                ],
            }
        # No direct ROI metric exists: SAT Promo (the Alfamart/B2B promo
        # program) has no promo-cost column beyond a free-text "mekanisme"
        # field, and SAT Promo only covers December 2024 with no prior-month
        # baseline in the same channel. The only measurable proxy is General
        # Trade Sell-In uplift (Nov vs Dec) for the same material codes - SAT
        # Promo's material_code is a SAP material code that is 100%
        # resolvable against sales_oct_dec_2024 (confirmed 1 Oct 2026, 77/77
        # materials matched), so this is a valid (if indirect/"halo effect")
        # proxy, not a guess. Offer the 3 variants we can actually compute
        # instead of refusing outright - this is a material change from the
        # earlier "ROI/uplift data not available" refusal.
        # A clarification answer that still carries the original question's
        # wording (contextualize_question() prepends it) would otherwise
        # re-trigger this same clarification forever, since "promo"/"ROI"
        # are still present. Check the ROI-proxy option discriminators
        # first, before the generic promo/ROI trigger below.
        roi_proxy_discriminators = {
            "promo_b2b_sellout_revenue_uplift": (
                "revenue uplift sell-out",
                "uplift sell-out",
                "uplift sellout",
                "uplift b2b",
                "uplift alfamart",
                "penjualan sell-out",
                "sell-out uplift",
                "sellout uplift",
                "partner sell-out",
            ),
            "promo_b2b_sellout_volume_uplift": (
                "volume uplift sell-out",
                "volume uplift b2b",
                "qty uplift sell-out",
                "qty uplift b2b",
            ),
            "promo_material_revenue_uplift": (
                "revenue uplift",
                "penjualan general trade",
                "dampak penjualan general trade",
                "keluarkan penjualan general trade",
            ),
            "promo_material_volume_uplift": (
                "volume uplift",
                "volume/qty uplift",
                "qty uplift",
                "volume general trade",
                "qty general trade",
            ),
            "promo_material_margin_uplift": ("margin uplift", "margin general trade"),
        }
        roi_proxy_selected = [
            metric
            for metric, terms in roi_proxy_discriminators.items()
            if any(_normalize(term) in normalized for term in terms)
        ]
        # User pasted the clarification's own proxy description (ID/EN) instead
        # of the short metric label - treat Nov-vs-Dec General Trade as revenue.
        if (
            not roi_proxy_selected
            and "generaltrade" in normalized
            and "november" in normalized
            and "desember" in normalized
            and ("promo" in normalized or "alfamart" in normalized or "roi" in normalized)
        ):
            roi_proxy_selected = ["promo_material_revenue_uplift"]
        if len(roi_proxy_selected) == 1:
            metric = roi_proxy_selected[0]
            return {
                "status": "resolved",
                "metric": metric,
                "matched_alias": "promo_roi_proxy_choice",
                "definition": self.metric_definition(metric),
                "dimension_mismatch": [],
            }
        requests_promo_rank = any(
            term in normalized
            for term in ("terbaik", "tertinggi", "terbesar", "top", "rank", "paling", "observasi", "jumlah")
        )
        if (
            mentions_promo
            and requests_promo_attribution
            and requests_promo_rank
            and "rekomendasi" not in normalized
        ):
            return {
                "status": "resolved",
                "metric": "promo_material_revenue_uplift",
                "matched_alias": "promo_uplift_rank",
                "definition": self.metric_definition("promo_material_revenue_uplift"),
                "dimension_mismatch": [],
            }
        if mentions_promo and requests_promo_rank and any(
            term in normalized for term in ("observasi", "observation", "jumlah", "count")
        ):
            return {
                "status": "resolved",
                "metric": "promo_observation_count",
                "matched_alias": "promo_observation_rank",
                "definition": self.metric_definition("promo_observation_count"),
                "dimension_mismatch": [],
            }
        requests_promo_status_distribution = (
            "programstatus" in normalized
            or "statusprogram" in normalized
            or ("distribusi" in normalized and "status" in normalized)
        )
        if mentions_promo and requests_promo_status_distribution:
            return {
                "status": "resolved",
                "metric": "promo_observation_count",
                "matched_alias": "promo_program_status_distribution",
                "definition": self.metric_definition("promo_observation_count"),
                "dimension_mismatch": [],
            }
        mentions_partner_sellout = any(
            term in normalized
            for term in ("sellout", "b2b", "alfamart", "partnersellout", "channelpartner")
        )
        if (
            mentions_promo
            and requests_promo_attribution
            and mentions_partner_sellout
            and "generaltrade" not in normalized
        ):
            wants_volume = any(
                term in normalized for term in ("volume", "qty", "quantity", "kuantitas")
            )
            metric = (
                "promo_b2b_sellout_volume_uplift"
                if wants_volume
                else "promo_b2b_sellout_revenue_uplift"
            )
            return {
                "status": "resolved",
                "metric": metric,
                "matched_alias": "promo_b2b_sellout_proxy",
                "definition": self.metric_definition(metric),
                "dimension_mismatch": [],
            }
        if mentions_promo and (requests_promo_attribution or requests_unavailable_promo_period):
            return {
                "status": "needs_clarification",
                "reason": "promo_roi_proxy_choice",
                "question": (
                    "TEMPO tidak memiliki data biaya promo atau ROI langsung untuk "
                    "SAT Promo (Alfamart) - data yang tersedia hanya deskripsi "
                    "mekanisme promo (teks bebas), bukan nilai biaya terstruktur, dan "
                    "SAT Promo hanya mencakup Desember 2024 tanpa baseline bulan "
                    "sebelumnya di channel yang sama. Proxy yang bisa dihitung: (1) uplift "
                    "sell-out B2B/Alfamart Nov vs Des untuk material promo yang sama, atau "
                    "(2) dampak penjualan General Trade untuk material yang sama. Metrik "
                    "mana yang Anda mau?"
                ),
                "options": [
                    {
                        "metric": "promo_b2b_sellout_revenue_uplift",
                        "label": "Revenue Uplift (Rp, B2B sell-out, proxy)",
                    },
                    {
                        "metric": "promo_b2b_sellout_volume_uplift",
                        "label": "Volume/Qty Uplift (B2B sell-out, proxy)",
                    },
                    {
                        "metric": "promo_material_revenue_uplift",
                        "label": "Revenue Uplift (Rp, General Trade, proxy)",
                    },
                    {
                        "metric": "promo_material_volume_uplift",
                        "label": "Volume/Qty Uplift (General Trade, proxy)",
                    },
                    {
                        "metric": "promo_material_margin_uplift",
                        "label": "Margin Uplift (Rp, General Trade, pakai COGS, proxy)",
                    },
                ],
            }

        # Tempo explicitly confirmed on 28 Sep 2026 that DC Stock and Store
        # Stock are positions at different analysis levels and must not be
        # added into a synthetic "total pipeline". Catch that request before
        # the generic stock-scope ambiguity (or alias scoring) can silently
        # select just one of the two published metrics.
        mentions_dc_level = any(
            term in normalized
            for term in (
                "dcstock", "stokdc", "stockdc", "dcpartner",
                "distributioncenter", "dcmana",
            )
        ) or "dc" in words
        mentions_store_level = any(
            term in normalized
            for term in (
                "storestock", "stokstore", "stockstore", "store",
                "stoktoko", "stokditoko", "stocktoko", "stockditoko",
                "tokoretail", "stokretail",
            )
        ) or bool(words & {"store", "toko", "retail"})
        requests_combination = any(
            term in normalized
            for term in (
                "totalpipeline",
                "jumlahkan",
                "penjumlahan",
                "gabungan",
                "digabung",
                "combined",
                "combine",
                "sumof",
                "totalstok",
                "totalstock",
                "gabungkan",
            )
        ) or bool(words & {"jumlah", "total"})
        if mentions_dc_level and mentions_store_level and requests_combination:
            return {
                "status": "needs_clarification",
                "reason": "sat_idm_stock_level_aggregation",
                "question": (
                    "DC Stock dan Store Stock berada pada level analisis "
                    "berbeda dan tidak boleh dijumlahkan sebagai total "
                    "pipeline. Pilih quantity atau value pada level DC "
                    "atau store; saya dapat menampilkannya berdampingan "
                    "sebagai metrik terpisah."
                ),
                "options": [
                    {
                        "metric": "sat_dc_stock_quantity",
                        "label": "DC Stock Quantity",
                    },
                    {
                        "metric": "sat_store_stock_quantity",
                        "label": "Store Stock Quantity",
                    },
                    {
                        "metric": "sat_dc_stock_value",
                        "label": "DC Stock Value",
                    },
                    {
                        "metric": "sat_store_stock_value",
                        "label": "Store Stock Value",
                    },
                ],
            }
        # "Bandingkan"/"vs" is a different, valid request from "jumlahkan" -
        # the user wants to SEE both levels side by side, not sum them into
        # one number (which Tempo explicitly prohibited, see above). No
        # single compile_governed() call can return two stock-level columns
        # at once, so route this to two explicit metric choices instead of
        # the generic 4-way stock_scope ambiguity below, which doesn't make
        # clear that both can be asked back-to-back for a side-by-side view.
        mentions_comparison = any(
            term in normalized for term in ("bandingkan", "dibandingkan", "perbandingan", "vs", "versus")
        )
        if mentions_dc_level and mentions_store_level and mentions_comparison and not requests_combination:
            wants_value = any(term in normalized for term in ("nilai", "value", "rupiah", "idr"))
            return {
                "status": "needs_clarification",
                "reason": "sat_idm_stock_level_comparison",
                "question": (
                    "DC Stock dan Store Stock berada pada level analisis "
                    "berbeda dan ditampilkan sebagai metrik terpisah, bukan "
                    "satu angka gabungan. Saya bisa tunjukkan keduanya - "
                    "tanyakan dulu salah satu di bawah, lalu lanjutkan "
                    "dengan yang satunya untuk melihat perbandingannya."
                ),
                "options": [
                    {
                        "metric": "sat_dc_stock_value" if wants_value else "sat_dc_stock_quantity",
                        "label": "DC Stock " + ("Value" if wants_value else "Quantity"),
                    },
                    {
                        "metric": "sat_store_stock_value" if wants_value else "sat_store_stock_quantity",
                        "label": "Store Stock " + ("Value" if wants_value else "Quantity"),
                    },
                ],
            }

        # An explicit partner-DC or retail-store phrase already answers the
        # stock-scope question. Let resolve_metric route it directly instead
        # of asking the same clarification again.
        mentions_stock_language = any(
            term in normalized for term in ("stock", "stok", "inventory", "persediaan")
        )
        if mentions_stock_language and mentions_dc_level != mentions_store_level:
            return None

        for ambiguity in self.governance.get("ambiguities", []):
            # "Out of stock" is the published SAT OOS KPI, not a request to
            # choose between warehouse, partner-DC, and retail-store stock.
            if ambiguity.get("name") == "stock_scope" and any(
                term in normalized for term in ("oos", "outofstock", "kehabisan", "kosong")
            ):
                continue
            # "Stok konsinyasi" has its own published metric
            # (stock_tempo_consignment_qty) that already implies the Tempo
            # warehouse scope - it does not need the generic
            # warehouse/DC/store clarification.
            if ambiguity.get("name") == "stock_scope" and any(
                term in normalized for term in ("konsinyasi", "consignment")
            ):
                continue
            if (
                ambiguity.get("name") == "sales_stage"
                and "salesoffice" in normalized
                and not any(
                    _normalize(term) in normalized
                    for term in ("revenue", "pendapatan", "nilai penjualan", "gross sales")
                )
            ):
                continue
            # "toko"/"outlet"/"gerai"/"e-store" language can only ever refer
            # to the B2B/Sell-Out store-level grain - Sell-In's base datasets
            # (monthly_executive, material_360) have no outlet/e_store field
            # at all, so there is nothing to disambiguate UNLESS the
            # question also explicitly asks to compare/combine with
            # Sell-In/Tempo/general trade.
            if ambiguity.get("name") == "sales_stage" and any(
                term in normalized for term in ("toko", "outlet", "gerai", "estore", "e-store")
            ) and not any(
                _normalize(term) in normalized
                for term in ("sell-in", "sell in", "tempo ke customer", "general trade", "gross billing")
            ):
                continue
            # A question asking for the RATIO/variance BETWEEN Sell-In and
            # Sell-Out ("rasio penjualan partner terhadap penjualan tempo")
            # mentions "penjualan" twice but is not choosing one stage over
            # the other - it wants the reconciliation metric that relates
            # both. Let ratio_direction (below, more specific) handle it
            # instead of sales_stage intercepting on the generic trigger.
            if ambiguity.get("name") == "sales_stage" and any(
                term in normalized for term in ("rasio", "ratio", "selisih", "gap", "variance")
            ):
                continue
            if not any(
                _normalize(str(term)) in normalized
                for term in ambiguity.get("trigger_terms", [])
            ):
                continue
            selected = []
            for option in ambiguity.get("options", []):
                if any(
                    _normalize(str(term)) in normalized
                    for term in option.get("discriminators", [])
                ):
                    selected.append(option)
            if len(selected) == 1:
                return None
            return {
                "status": "needs_clarification",
                "reason": ambiguity["name"],
                "question": ambiguity["question"],
                "options": ambiguity.get("options", []),
            }
        return None

    def resolve_metric(self, question: str) -> dict[str, Any]:
        ambiguity = self.resolve_ambiguity(question)
        if ambiguity:
            return ambiguity

        if _is_semantic_registry_catalog(self.metrics):
            return self._resolve_semantic_registry_catalog_metric(question)

        normalized = _normalize(question)
        mentions_stock = any(term in normalized for term in ("stock", "stok", "inventory", "persediaan"))
        words = set(re.findall(r"[a-z0-9]+", question.casefold()))
        mentions_partner_dc = any(
            term in normalized
            for term in (
                "dcstock", "stokdc", "stockdc", "dcpartner",
                "distributioncenter", "dcmana",
            )
        ) or "dc" in words
        mentions_retail_store = any(
            term in normalized
            for term in (
                "storestock", "stokstore", "stockstore", "stoktoko",
                "stokditoko", "stocktoko", "stockditoko", "tokoretail",
                "stokretail", "retailstock",
            )
        ) or bool(words & {"store", "toko", "retail"})
        explicit_short_choice = normalized in {"dc", "dcpartner", "store", "toko", "retail", "stokdcpartner", "stokstore", "stoktoko"}
        explicit_dc_ranking = "dcmana" in normalized
        explicit_low_stock_ranking = "mana" in words and bool(
            words & {"rendah", "terendah", "kecil", "terkecil", "sedikit"}
        )
        if (
            mentions_stock
            or explicit_short_choice
            or explicit_dc_ranking
            or explicit_low_stock_ranking
        ) and (
            mentions_partner_dc != mentions_retail_store
        ):
            wants_value = any(term in normalized for term in ("nilai", "value", "rupiah", "idr"))
            if mentions_partner_dc:
                metric_name = "sat_dc_stock_value" if wants_value else "sat_dc_stock_quantity"
            else:
                metric_name = "sat_store_stock_value" if wants_value else "sat_store_stock_quantity"
            return {
                "status": "resolved",
                "metric": metric_name,
                "matched_alias": "explicit_stock_level",
                "definition": self.metric_definition(metric_name),
                "dimension_mismatch": [],
            }

        dimension_terms = {
            "material": ("material", "sku", "produk", "product", "products", "barang", "item"),
            "customer": ("customer", "pelanggan"),
            # TEMPO confirmed that partner/B2B branch and TEMPO sales office
            # are genuinely different dimensions. Keep their routing hints
            # separate so a branch-qualified B2B question cannot receive the
            # generic company-month bonus and fall through to Gross Sales.
            # "cabang" is listed under both - it is the common Indonesian word
            # for either a B2B partner branch or a Tempo sales office, and
            # which one a question means is decided by the sales_stage
            # ambiguity (Sell-In vs B2B/Sell-Out) resolving first, not by
            # this dimension hint alone; resolve_metric's per-metric alias
            # scoring then picks the matching domain's metric.
            "branch": ("branch", "cabang partner", "branch b2b", "cabang"),
            "sales_off": ("sales off", "sales_off", "cabang"),
            "sales_office": ("sales office", "kantor penjualan", "office", "cabang"),
            "fill_rate_band": ("fill rate band", "kategori fill", "low fill", "per band", "fill rate per band"),
            "calmonth": ("bulan", "bulanan", "month", "trend", "tren"),
        }
        hinted_dimensions = {
            dimension
            for dimension, terms in dimension_terms.items()
            if any(_normalize(term) in normalized for term in terms)
        }
        # "sales office" folds to salesoffice, which falsely contains the
        # sales_off hint "salesoff" - prefer sales_office for Tempo office metrics.
        if "salesoffice" in normalized or "kantorpenjualan" in normalized:
            hinted_dimensions.discard("sales_off")
            hinted_dimensions.add("sales_office")
        company_scope = any(
            _normalize(term) in normalized
            for term in ("company", "perusahaan", "tempo total", "total tempo")
        )
        # A question with no dimension hint beyond calmonth ("Fill Rate per
        # bulan?", no mention of "material"/"sku"/"produk"/"cabang"/etc.) is
        # most naturally read as asking for the company-wide aggregate, not
        # a specific breakdown - several metrics share generic aliases like
        # "fill rate" (company/material/service-level fill rate all do), so
        # without this the shortest alias wins by token-count alone and a
        # plain, unqualified question resolves to a granular per-material
        # metric instead of the aggregate one golden_questions.yaml expects.
        unqualified_scope = hinted_dimensions <= {"calmonth"}

        question_tokens = _tokenize(question)
        candidates: list[tuple[int, str, str]] = []
        for metric_name in self.metrics:
            config = self.metric_configs[metric_name]
            allowed_dimensions = set(config.get("allowed_dimensions", []))
            dataset_name = config.get("base_dataset")
            for alias in self.metric_aliases(metric_name):
                normalized_alias = _normalize(alias)
                alias_tokens = _tokenize(alias)
                # Two ways an alias can match a question, checked together so
                # neither phrasing style is required: (1) an exact,
                # whitespace-stripped substring match - the strongest signal,
                # since it means the alias's exact wording appears verbatim;
                # (2) every content word (stopwords excluded) in the alias
                # also appears somewhere in the question, in any order - this
                # is what makes phrasing like "nilai Sell-In terbesar" match
                # a synonym written as "material sell-in value" (both reduce
                # to the shared token {"sell", "in"} once stopwords like
                # "nilai"/"value" are dropped), without resorting to an
                # LLM/embedding call for what's meant to stay a deterministic,
                # governed lookup.
                is_substring_match = bool(normalized_alias) and normalized_alias in normalized
                # A token-only fuzzy match needs at least two meaningful
                # tokens. Phrases such as "bill value" collapse to the lone
                # token "bill" after bilingual value/nilai stopword removal;
                # allowing that single token to match would route BILL_QTY to
                # Gross Billing Value. A literal one-word alias (GBV, OOS,
                # dcstock) still resolves through the stronger substring path.
                is_token_match = len(alias_tokens) >= 2 and alias_tokens <= question_tokens
                if not (is_substring_match or is_token_match):
                    continue
                score = len(normalized_alias) if is_substring_match else len(alias_tokens)
                if not is_substring_match:
                    # Token-overlap matches are inherently less certain than
                    # an exact substring (word order/context is ignored), so
                    # rank every substring match above every token-only match
                    # regardless of alias length.
                    score -= 1000
                score += 100 * len(hinted_dimensions & allowed_dimensions)
                if any(
                    dimension in metric_name
                    for dimension in hinted_dimensions
                ):
                    score += 50
                if company_scope and dataset_name == "monthly_executive":
                    score += 100
                if unqualified_scope and allowed_dimensions <= {"calmonth"}:
                    score += 75
                candidates.append((score, metric_name, alias))
        if not candidates:
            return {
                "status": "unsupported",
                "reason": "no_published_metric_match",
                "question": self.governance.get("unknown_metric_question"),
                "capabilities": self.capability_summary(),
            }
        candidates.sort(reverse=True)
        _, metric_name, alias = candidates[0]
        allowed_dimensions = set(self.metric_configs[metric_name].get("allowed_dimensions", []))
        # Signal for resolve_with_llm_fallback(): the question hinted at a
        # dimension (e.g. "produk"/"product" -> material) that the winning
        # metric's allowed_dimensions does NOT support. This is how a
        # deterministic match can still be the WRONG metric - e.g. "top 5
        # produk" matching company-level gross_billing_value (calmonth-only)
        # instead of the material-grain metric that actually supports a
        # product breakdown - without the matcher ever reporting
        # "unsupported". A non-empty mismatch does not change status or
        # metric here; it only tells the caller this deterministic result is
        # less certain and worth a second opinion.
        #
        # "cabang" ambiguously hints branch/sales_off/sales_office all at
        # once (see the dimension_terms comment above) - it is the one
        # Indonesian word for a B2B partner branch, a Tempo sales office,
        # and two differently-named physical columns for the latter
        # concept across gold views. The winning metric's own alias scoring
        # already picked the correct domain (B2B vs Tempo sales); once ANY
        # member of this synonym group is actually covered by that metric's
        # allowed_dimensions, the other members must not be reported as
        # unmet - they were never separate, unanswered requests, just
        # alternate readings of the one "cabang" the question asked for.
        cabang_synonyms = {"branch", "sales_off", "sales_office"}
        if hinted_dimensions & cabang_synonyms & allowed_dimensions:
            hinted_dimensions = hinted_dimensions - cabang_synonyms
        dimension_mismatch = sorted(hinted_dimensions - {"calmonth"} - allowed_dimensions)
        return {
            "status": "resolved",
            "metric": metric_name,
            "matched_alias": alias,
            "definition": self.metric_definition(metric_name),
            "dimension_mismatch": dimension_mismatch,
        }

    def metric_catalog_for_classification(self) -> list[dict[str, Any]]:
        """Closed list of {name, description, allowed_dimensions} for every
        governed metric, used as the candidate set an LLM fallback
        classifier picks from - either when the deterministic token matcher
        in resolve_metric() finds no match at all, or when it matches but
        flags a dimension_mismatch (picked a metric whose allowed_dimensions
        doesn't cover a dimension the question hinted at). allowed_dimensions
        is included specifically for the second case: two metrics can have
        near-identical descriptions (e.g. gross_billing_value "Official
        TEMPO revenue" vs material_sell_in_value "Sell-In Gross Billing
        Value by material and month") and be indistinguishable by text
        alone - the classifier needs to see which one actually supports a
        material/product breakdown to pick correctly. Kept separate from
        resolve_metric so the primary path stays a pure, LLM-free lookup -
        this only feeds a downstream fallback, never replaces the
        deterministic result when one exists."""
        result = []
        for name, metric in self.metrics.items():
            config = self.metric_configs.get(name, {})
            result.append(
                {
                    "name": name,
                    "description": str(metric.get("description") or ""),
                    "allowed_dimensions": config.get("allowed_dimensions", []),
                }
            )
        return result

    def metric_definition(self, metric_name: str) -> dict[str, Any]:
        if metric_name not in self.metrics:
            raise KeyError(metric_name)
        metric = self.metrics[metric_name]
        config = self.metric_configs[metric_name]
        return {
            "name": metric_name,
            "metric_id": config.get("metric_id"),
            "description": metric.get("description"),
            "expression": self.ansi_expression(metric),
            "datatype": metric.get("datatype"),
            "base_dataset": config.get("base_dataset"),
            "allowed_dimensions": config.get("allowed_dimensions", []),
            "required_filters": config.get("required_filters", []),
            "row_filter": config.get("row_filter"),
            "governance_status": config.get("governance_status"),
            "business_approval_status": config.get("business_approval_status"),
            "original_kpi_id": config.get("original_kpi_id"),
            "unit_format": config.get("unit_format"),
            "ai_context": metric.get("ai_context", {}),
        }

    def capability_summary(self) -> dict[str, Any]:
        return {
            "model": self.model["name"],
            "scope": self.governance.get("scope", {}),
            "datasets": [
                {
                    "name": name,
                    "description": dataset.get("description"),
                    "source": dataset.get("source"),
                }
                for name, dataset in self.datasets.items()
            ],
            "metrics": [
                self.metric_definition(metric_name) for metric_name in self.metrics
            ],
            "examples": [
                item["question"]
                for item in self.golden_questions.get("questions", [])
                if item.get("expected_status") in {"supported", "supported_with_caveat"}
            ][:8],
        }
