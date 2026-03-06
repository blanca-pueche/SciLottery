import re

import requests
import time
import numpy as np
import pandas as pd


BASE_URL = "https://api.openalex.org"

def authors_working_at_institution_in_year(inst_id: str, year: int, email: str, per_page: int = 10):
    """
    Returns a set of AIDs (A...) for authors who:
      (1) have last_known_institutions containing inst_id  (proxy: currently at institution)
      (2) have an affiliations entry for inst_id whose years include `year`
    """
    inst_id = inst_id.split("/")[-1]
    if inst_id[0].lower() == "i":
        inst_id = "I" + inst_id[1:]

    aids = set()
    msg=''
    cursor = "*"

    # Prefilter: authors who ever had the institution (reduces search space)
    prefilter = f"affiliations.institution.id:{inst_id}"

    while cursor:
        params = {
            "filter": prefilter,
            "per_page": per_page,
            "cursor": cursor,
            "select": "id,last_known_institutions,affiliations",
            "mailto": email,
        }

        try:
            r = requests.get(f"{BASE_URL}/authors", params=params, timeout=60)
            r.raise_for_status()
            data = r.json()

            for a in data.get("results", []):
                lkis = a.get("last_known_institutions") or []
                lk_ids = {x["id"].split("/")[-1] for x in lkis if isinstance(x, dict) and "id" in x}
                if inst_id not in lk_ids:
                    continue

                ok_year = False
                for aff in a.get("affiliations") or []:
                    inst_aff_id = aff.get("institution", {}).get("id", "").split("/")[-1]
                    years = aff.get("years") or []
                    if inst_aff_id == inst_id and year in years:
                        ok_year = True
                        break

                if ok_year:
                    aids.add(a["id"].split("/")[-1])

            cursor = data.get("meta", {}).get("next_cursor")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                msg = (f"Rate limit hit for institution {inst_id}. Returning partial results ({len(aids)} authors).")
                break
            else:
                msg = (f"HTTP error {e.response.status_code} for institution {inst_id}. Continuing anyway.")
                break
        except Exception as e:
            msg = (f"Error retrieving authors for institution {inst_id}: {e}. Continuing anyway.")
            break

    return aids, msg

def get_json_with_retry(endpoint, params, max_retries=5, timeout=60):
    delay = 1.0
    for attempt in range(max_retries):
        try:
            r = requests.get(
                f"{BASE_URL}/{endpoint}",
                params=params,
                timeout=timeout
            )
            r.raise_for_status()
            return r.json()

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            # Retry only on transient server errors
            if status in (502, 503, 504):
                if attempt == max_retries - 1:
                    raise
                time.sleep(delay)
                delay *= 2
            else:
                raise

def get_author_work_ids_in_year_range(aid: str, y0: int, y1: int, mailto: str, per_page: int = 200, sleep_s: float = 0.05):
    """Return list of work IDs (W...) for works by author aid with publication_year in [y0, y1]."""
    work_ids = []
    cursor = "*"
    while cursor:
        params = {
            "filter": f"authorships.author.id:{aid},publication_year:{y0}-{y1}",
            "select": "id",
            "per_page": per_page,
            "cursor": cursor,
            "mailto": mailto,
        }
        data = get_json_with_retry("works", params)
        for w in data.get("results", []):
            work_ids.append(w["id"].split("/")[-1])  # W...
        cursor = data["meta"].get("next_cursor")
        if sleep_s:
            time.sleep(sleep_s)

    # De-duplicate while preserving order (usually unnecessary, but safe)
    seen, uniq = set(), []
    for wid in work_ids:
        if wid not in seen:
            seen.add(wid)
            uniq.append(wid)
    return uniq

def citation_count_for_work_in_year_range(
    wid: str, y0: int, y1: int, mailto: str, sleep_s: float = 0.0
) -> int:
    params = {
        "filter": f"cites:{wid},publication_year:{y0}-{y1}",
        "per_page": 1,
        "mailto": mailto,
    }
    data = get_json_with_retry("works", params)
    time.sleep(sleep_s)
    return int(data["meta"]["count"])

def citation_distribution_for_work_set(work_ids, y0: int, y1: int, mailto: str,
                                       sleep_s: float = 0.0):
    """Return list of per-work citation counts within [y0,y1] for a UNIQUE set of works."""
    dist = []
    for wid in work_ids:
        dist.append(citation_count_for_work_in_year_range(wid, y0, y1, mailto=mailto, sleep_s=sleep_s))
    return dist

def build_author_df_and_unique_work_distributions(aids, Y: int, mailto: str,
                                                  sleep_s: float = 0.0,
                                                  per_page_works: int = 200):
    """
    Returns:
      df: columns [authorID, count1, citations1, maxCitation1, works1, count2, citations2, maxCitation2, works2]
      dist1: list of citation counts for UNIQUE works in period1 across ALL authors
      dist2: list of citation counts for UNIQUE works in period2 across ALL authors
    """
    w1 = (Y - 5, Y - 1)
    w2 = (Y, Y + 4)

    rows = []
    all_works1 = set()
    all_works2 = set()
    counter = 0
    for aid in aids:
        # normalize AID if user passed URL
        aid_norm = aid.split("/")[-1].strip()

        try:
          works1 = get_author_work_ids_in_year_range(aid_norm, w1[0], w1[1], mailto=mailto,
                                                    per_page=per_page_works, sleep_s=sleep_s)
          works2 = get_author_work_ids_in_year_range(aid_norm, w2[0], w2[1], mailto=mailto,
                                                    per_page=per_page_works, sleep_s=sleep_s)

          all_works1.update(works1)
          all_works2.update(works2)

          # Per-author aggregates (no coauthor overweighting issue here; it’s the author’s own set)
          dist1_author = citation_distribution_for_work_set(works1, w1[0], w1[1], mailto=mailto, sleep_s=sleep_s) if works1 else []
          dist2_author = citation_distribution_for_work_set(works2, w2[0], w2[1], mailto=mailto, sleep_s=sleep_s) if works2 else []

          row = {
              "authorID": aid_norm,
              "count1": len(works1),
              "citations1": int(sum(dist1_author)),
              "maxCitation1": int(max(dist1_author)) if dist1_author else 0,
              "works1": works1,
              "count2": len(works2),
              "citations2": int(sum(dist2_author)),
              "maxCitation2": int(max(dist2_author)) if dist2_author else 0,
              "works2": works2,
          }
          print(counter,row)
          rows.append(row)
        except Exception as e:
            print(e)
        counter+=1

    df = pd.DataFrame(
        rows,
        columns=["authorID", "count1", "citations1", "maxCitation1", "works1",
                 "count2", "citations2", "maxCitation2", "works2"]
    )

    # UNIQUE work distributions across the cohort (no overweighting of coauthored works)
    uniq_works1 = sorted(all_works1)
    uniq_works2 = sorted(all_works2)

    return df


def sanitizeIds(input_str, st, prefix, max_ids=200):
    """
    Clean and validate input IDs (author or institution).

    - Only alphanumeric, dash, underscore, and dot allowed.
    - IDs must be comma-separated.
    - Strips whitespace.
    - Limits total number of IDs to max_ids.
    """
    if not input_str:
        return []

    ids = [x.strip() for x in input_str.split(",") if x.strip()]
    valid_ids = []

    pattern = f"^{prefix}\\d+$"  # e.g., '^A\d+$' or '^i\d+$'

    for id_ in ids:
        if re.match(pattern, id_):
            valid_ids.append(id_)
        else:
            st.warning(f"Invalid ID skipped: {id_}")

    if len(valid_ids) > max_ids:
        st.warning(f"Only the first {max_ids} IDs will be used.")
        valid_ids = valid_ids[:max_ids]

    if not valid_ids:
        st.error(f"No valid IDs provided with prefix '{prefix}'.")

    return valid_ids

def apply_floor_cap_proportionally(b, B, b_min=0.0, b_max=np.inf, max_iter=200, tol=1e-9):
    """
    Enforce per-researcher minimum/maximum funding while keeping sum(b)=B.
    Simple iterative waterfilling-style adjustment.

    Parameters
    ----------
    b : array-like
        Initial allocations (nonnegative).
    B : float
        Total budget.
    b_min : float
        Minimum allocation per researcher (optional).
    b_max : float
        Maximum allocation per researcher (optional).
    max_iter : int
        Max number of adjustment iterations.
    tol : float
        Convergence tolerance.

    Returns
    -------
    np.ndarray
        Adjusted allocations summing to B (up to numerical tolerance).
    """
    b = np.asarray(b, dtype=float).copy()
    n = len(b)
    if n == 0:
        return b

    # Apply minimum
    if b_min > 0:
        b = np.maximum(b, b_min)

    # If minimums already exceed budget, scale down proportionally
    s = b.sum()
    if s > B and s > 0:
        return b * (B / s)

    # Iteratively enforce maximum and redistribute residual
    for _ in range(max_iter):
        b_prev = b.copy()

        # Cap
        over = b > b_max
        if np.any(over):
            b[over] = b_max

        total = b.sum()
        remaining = B - total

        if abs(remaining) < tol:
            break

        if remaining > 0:
            # redistribute extra to those not at max
            eligible = b < b_max - 1e-15
            if not np.any(eligible):
                break
            weights = b[eligible]
            if weights.sum() <= 1e-15:
                b[eligible] += remaining / eligible.sum()
            else:
                b[eligible] += remaining * (weights / weights.sum())
        else:
            # remove budget from those above min
            eligible = b > b_min + 1e-15
            if not np.any(eligible):
                break
            weights = b[eligible] - b_min
            if weights.sum() <= 1e-15:
                b[eligible] -= (-remaining) / eligible.sum()
            else:
                b[eligible] -= (-remaining) * (weights / weights.sum())

        if np.max(np.abs(b - b_prev)) < tol:
            break

    # Final normalization for small numerical drift
    s = b.sum()
    if s > 0:
        b *= (B / s)
    return b

def allocate_budget(df: pd.DataFrame, B: float, score_col: str,
    alpha: float = 0.3,          # exploration budget share (α)
    lambda_uniform: float = 0.8, # exploration mix (λ): λ*uniform + (1-λ)*score-proportional
    gamma: float = 1.5,          # exploitation concentration (γ)
    b_min: float = 0.0,          # optional floor (b_min)
    b_max: float = np.inf,       # optional cap (b_max)
    id_col: str = "authorID",
    add_columns: bool = True
) -> pd.DataFrame:
    """
    Deterministic hybrid allocation (paper notation):
      B_explore = α B
      b_i^explore = B_explore * [ λ(1/N) + (1-λ) s_i / Σ s ]
      B_exploit = (1-α) B
      b_i^exploit = B_exploit * [ s_i^γ / Σ s^γ ]
      b_i = b_i^explore + b_i^exploit
    with optional bounds b_min <= b_i <= b_max enforced while preserving Σ b_i = B.

    Parameters
    ----------
    df : DataFrame
        Must contain `score_col` and `id_col`.
    B : float
        Total budget.
    score_col : str
        Column name containing the score s_i (higher is better; not necessarily percentile).
    alpha, lambda_uniform, gamma : floats
        Policy hyperparameters (α, λ, γ).
    b_min, b_max : floats
        Optional floor/cap per researcher.
    id_col : str
        Identifier column (default "authorID").
    add_columns : bool
        If False, returns only [id_col, b_total].

    Returns
    -------
    DataFrame
        With columns: score_col, b_explore, b_exploit, b_total (and id_col).
    """
    if df is None or len(df) == 0:
        raise ValueError("df is empty.")
    if score_col not in df.columns:
        raise ValueError(f"score_col='{score_col}' not found in df.")
    if id_col not in df.columns:
        raise ValueError(f"id_col='{id_col}' not found in df.")
    if B <= 0:
        raise ValueError("B must be > 0.")
    if not (0 <= alpha <= 1):
        raise ValueError("alpha must be in [0,1].")
    if not (0 <= lambda_uniform <= 1):
        raise ValueError("lambda_uniform must be in [0,1].")
    if gamma <= 0:
        raise ValueError("gamma must be > 0.")
    if b_min < 0:
        raise ValueError("b_min must be >= 0.")
    if not (b_max > 0):
        raise ValueError("b_max must be > 0 (or np.inf).")
    if b_max < b_min:
        raise ValueError("b_max must be >= b_min.")

    out = df.copy()

    # Scores s_i (nonnegative)
    s = out[score_col].to_numpy(dtype=float)
    s = np.nan_to_num(s, nan=0.0, posinf=0.0, neginf=0.0)
    s = np.clip(s, 0.0, None)

    n = len(s)
    if n == 0:
        raise ValueError("df is empty after processing.")

    # If all scores are zero, fall back to uniform (still well-defined)
    if s.sum() <= 1e-15:
        s_norm = np.ones(n) / n
        s_gamma_norm = np.ones(n) / n
    else:
        s_norm = s / s.sum()
        s_gamma = np.power(s, gamma)
        if s_gamma.sum() <= 1e-15:
            s_gamma_norm = np.ones(n) / n
        else:
            s_gamma_norm = s_gamma / s_gamma.sum()

    # Exploration component
    B_explore = alpha * B
    uniform = np.ones(n) / n
    p_explore = lambda_uniform * uniform + (1.0 - lambda_uniform) * s_norm
    b_explore = B_explore * p_explore

    # Exploitation component
    B_exploit = (1.0 - alpha) * B
    b_exploit = B_exploit * s_gamma_norm

    # Total before bounds
    b_total = b_explore + b_exploit

    # Optional floor/cap
    if b_min > 0 or np.isfinite(b_max):
        b_total_adj = apply_floor_cap_proportionally(b_total, B, b_min=b_min, b_max=b_max)

        # After enforcing bounds, keep a best-effort decomposition by scaling components
        scale = b_total_adj / (b_total + 1e-18)
        b_explore = b_explore * scale
        b_exploit = b_exploit * scale
        b_total = b_total_adj

    out["b_explore"] = b_explore
    out["b_exploit"] = b_exploit
    out["b_total"] = b_total

    if not add_columns:
        return out[[id_col, "b_total"]].copy()

    return out


def utility_from_params(df, B, score_col, alpha, lambda_uniform, gamma,
                        target_col="avgPerc2", b_min=0.0, b_max=np.inf, id_col="authorID"):
    """
    Compute utility U = b · y where b is the allocated budget vector (b_total)
    and y is the realized/target outcome (avgPerc2 by default).
    """
    alloc = allocate_budget(
        df=df,
        B=B,
        score_col=score_col,
        alpha=alpha,
        lambda_uniform=lambda_uniform,
        gamma=gamma,
        b_min=b_min,
        b_max=b_max,
        id_col=id_col,
        add_columns=True
    )

    # Align and compute dot product
    b = alloc["b_total"].to_numpy(dtype=float)
    y = alloc[target_col].to_numpy(dtype=float)

    mask = np.isfinite(b) & np.isfinite(y)
    if mask.sum() == 0:
        return np.nan

    return float(np.dot(b[mask], y[mask]))

def checkValid(ids, letter, st):
    letter = letter.lower()
    cleaned_ids = [x.strip() for x in ids]

    valid_ids = [x for x in cleaned_ids if x.lower().startswith(letter)]
    invalid_ids = [x for x in cleaned_ids if not x.lower().startswith(letter)]

    if invalid_ids:
        st.warning(f"Removed invalid IDs (must start with '{letter.upper()}'): {', '.join(invalid_ids)}")

    return valid_ids
