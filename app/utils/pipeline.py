import re

import requests
import time
import numpy as np
import pandas as pd


BASE_URL = "https://api.openalex.org"

def authors_working_at_institution_in_year(
        inst_id: str,
        year: int,
        mailto: str,
        per_page: int = 200,
        min_total_works: int | None = None,
        min_total_citations: int | None = None):
    """
    Returns a set of AIDs (A...) for authors who:
      (1) have last_known_institutions containing inst_id
      (2) have an affiliations entry for inst_id whose years include `year`
      (3) optionally satisfy total works constraints
      (4) optionally satisfy minimum citation count
    """

    inst_id = inst_id.split("/")[-1]
    if inst_id[0].lower() == "i":
        inst_id = "I" + inst_id[1:]

    aids = set()
    msg=''
    cursor = "*"

    prefilter = f"affiliations.institution.id:{inst_id}"
    max_retries = 5
    retry_count = 0

    while cursor:
        params = {
            "filter": prefilter,
            "per_page": per_page,
            "cursor": cursor,
            "select": "id,last_known_institutions,affiliations,works_count,cited_by_count",
            "mailto": mailto,
        }
        try:
            r = requests.get(f"{BASE_URL}/authors", params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            for a in data.get("results", []):

                # (0) filters on works and citations
                wc = a.get("works_count", 0)
                cc = a.get("cited_by_count", 0)

                if min_total_works is not None and wc < min_total_works:
                    continue

                if min_total_citations is not None and cc < min_total_citations:
                    continue

                # (1) current/last includes institution
                lkis = a.get("last_known_institutions") or []
                lk_ids = {x["id"].split("/")[-1]
                          for x in lkis
                          if isinstance(x, dict) and "id" in x}

                if inst_id not in lk_ids:
                    continue

                # (2) affiliation history includes institution in target year
                ok_year = False
                for aff in a.get("affiliations") or []:
                    inst = aff.get("institution") or {}
                    inst_aff_id = inst.get("id", "").split("/")[-1] if inst.get("id") else ""
                    years = aff.get("years") or []

                    if inst_aff_id == inst_id and year in years:
                        ok_year = True
                        break

                if ok_year:
                    aids.add(a["id"].split("/")[-1])

            cursor = data.get("meta", {}).get("next_cursor")
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            if status == 429:
                wait_time = int(e.response.headers.get("Retry-After", 2))
                retry_count += 1
                msg = (
                    f"Rate limit hit for institution {inst_id}. "
                    f"Retry {retry_count}/{max_retries} after {wait_time}s..."
                )
                time.sleep(wait_time)
                if retry_count >= max_retries:
                    msg = (
                        f"Max retries reached for {inst_id}. "
                        f"Returning partial results ({len(aids)} authors)."
                    )
                    break
                continue
            else:
                msg = f"HTTP error {status} for institution {inst_id}. Skipping page."
                break

        except Exception as e:
            msg = f"Error retrieving authors for institution {inst_id}: {e}. Continuing anyway."
            break

    return aids, msg

def count_author_works_in_period(author_id: str, mailto: str,
                                 start_year: int,
                                 end_year: int) -> int:
    """
    Exact number of works for an author in a given institution and date range.
    """
    if author_id[0].lower() == "a":
        author_id = "A" + author_id[1:]
    filt = (
        f"authorships.author.id:{author_id},"
        f"from_publication_date:{start_year}-01-01,"
        f"to_publication_date:{end_year}-12-31"
    )

    params = {
        "filter": filt,
        "per_page": 1,   # we only need meta.count
        "mailto": mailto,
    }

    r = requests.get(f"{BASE_URL}/works", params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data.get("meta", {}).get("count", 0)

def count_author_works_in_period_safe(author_id: str, mailto: str,
                                      start_year: int, end_year: int,
                                      max_retries: int = 3) -> int | None:
    """
    Safe wrapper around count_author_works_in_period:
    retries a few times if request fails. Returns None if still failing.
    """
    for attempt in range(max_retries):
        try:
            return count_author_works_in_period(author_id, mailto, start_year, end_year)
        except requests.RequestException as e:
            # Rate limit or network error
            print(f"Attempt {attempt+1} failed for {author_id}: {e}")
            time.sleep(1 * (2 ** attempt))  # exponential backoff
    return None

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
    wid: str,
    y0: int,
    y1: int,
    mailto: str,
    sleep_s: float = 0.0,
    work_citation_cache: dict | None = None,
) -> int:
    """
    Return number of citations received by work `wid` from works published in [y0, y1].

    Since y0 and y1 are fixed during the run, the cache key is just `wid`.
    """
    if work_citation_cache is not None and wid in work_citation_cache:
        return work_citation_cache[wid]

    params = {
        "filter": f"cites:{wid},publication_year:{y0}-{y1}",
        "per_page": 1,
        "mailto": mailto,
    }
    data = get_json_with_retry("works", params)
    time.sleep(sleep_s)
    count = int(data["meta"]["count"])

    if work_citation_cache is not None:
        work_citation_cache[wid] = count

    return count

def citation_distribution_for_work_set(
    work_ids,
    y0: int,
    y1: int,
    mailto: str,
    sleep_s: float = 1,
    work_citation_cache: dict | None = None,
):
    """Return list of per-work citation counts within [y0, y1] for a unique set of works."""
    dist = []
    for wid in work_ids:
        dist.append(
            citation_count_for_work_in_year_range(
                wid,
                y0,
                y1,
                mailto=mailto,
                sleep_s=sleep_s,
                work_citation_cache=work_citation_cache,
            )
        )
    return dist

def build_author_df_and_unique_work_distributions(
    aids,
    y0: int,
    y1: int,
    mailto: str,
    sleep_s: float = 1,
    per_page_works: int = 200,
    work_citation_cache: dict | None = None,
):
    """
    Returns:
      df: columns [authorID, count1, citations1, maxCitation1, works1]
      dist1_unique: citation counts for UNIQUE works across all authors
      work_citation_cache: local cache wid -> citation_count
    """
    if work_citation_cache is None:
        work_citation_cache = {}

    rows = []
    all_works1 = set()
    counter = 0

    for aid in aids:
        aid_norm = aid.split("/")[-1].strip()

        try:
            works1 = get_author_work_ids_in_year_range(
                aid_norm,
                y0,
                y1,
                mailto=mailto,
                per_page=per_page_works,
                sleep_s=sleep_s,
            )

            works1 = set(works1)  # just in case
            all_works1.update(works1)

            dist1_author = citation_distribution_for_work_set(
                works1,
                y0,
                y1,
                mailto=mailto,
                sleep_s=sleep_s,
                work_citation_cache=work_citation_cache,
            ) if works1 else []

            row = {
                "authorID": aid_norm,
                "count1": len(works1),
                "citations1": int(sum(dist1_author)),
                "maxCitation1": int(max(dist1_author)) if dist1_author else 0,
            }
            print(counter, row)
            rows.append(row)

        except Exception as e:
            print(e)

        counter += 1

    df = pd.DataFrame(
        rows,
        columns=["authorID", "count1", "citations1", "maxCitation1"]
    )

    # unique-work distribution across all authors
    dist1_unique = [
        citation_count_for_work_in_year_range(
            wid,
            y0,
            y1,
            mailto=mailto,
            sleep_s=sleep_s,
            work_citation_cache=work_citation_cache,
        )
        for wid in all_works1
    ]

    return df, dist1_unique, work_citation_cache

def ensure_rank_cols(df, cols):
    """
    Ensure normalized rank columns exist for each col in cols.
    Best -> 0, worst -> 1. Adds <col>_rank if missing.
    """
    out = df.copy()
    for c in cols:
        rcol = f"{c}_rank"
        if rcol in out.columns:
            continue
        r = out[c].rank(method="average", ascending=False)
        denom = r.max() - 1
        out[rcol] = 0.5 if denom == 0 else (r - 1) / denom
    return out


def build_score_from_ranks(df, rank_cols, weights=None, clip_eps=1e-9):
    """
    Convert rank columns (0 best .. 1 worst) into a score s in [0,1]:
      goodness = 1 - rank
      s = weighted average goodness
    """
    if weights is None:
        weights = {c: 1.0 for c in rank_cols}
    w = np.array([weights.get(c, 0.0) for c in rank_cols], dtype=float)
    if np.all(w == 0):
        raise ValueError("All weights are zero.")
    w = w / w.sum()

    G = np.vstack([(1.0 - df[c].to_numpy(dtype=float)) for c in rank_cols]).T  # shape (n,k)
    s = (G * w).sum(axis=1)
    # avoid exact zeros (helps when raising to gamma)
    s = np.clip(s, clip_eps, 1.0)
    return s

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
        if re.match(pattern, id_, re.IGNORECASE):
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

def allocate_budget(
    df,
    B,
    alpha=0.3,          # fraction for exploration (uniform/option value)
    gamma=1.5,          # concentration on high-score for exploitation
    lambda_uniform=0.8, # exploration mix: lambda*uniform + (1-lambda)*score
    score_weights=None, # weights for rank cols used in score
    use_rank_cols=("count1_rank","citations1_rank","maxCitation1_rank"),
    b_floor=0.0,
    b_cap=np.inf,
    add_columns=True
):
    """
    Returns a new DataFrame with:
      - score s
      - b_explore, b_exploit, b_total
      - (optionally) floors/caps applied to b_total
    """
    if not (0 <= alpha <= 1):
        raise ValueError("alpha must be in [0,1].")
    if not (0 <= lambda_uniform <= 1):
        raise ValueError("lambda_uniform must be in [0,1].")
    if gamma <= 0:
        raise ValueError("gamma must be > 0.")

    out = df.copy()
    n = len(out)
    if n == 0:
        raise ValueError("df is empty.")

    # Ensure needed rank cols exist (if user gave raw cols only)
    base_cols = [c.replace("_rank", "") for c in use_rank_cols]
    out = ensure_rank_cols(out, base_cols)

    # Build score from rank cols
    s = build_score_from_ranks(out, list(use_rank_cols), weights=score_weights)
    out["score"] = s

    # Exploration part
    B_explore = alpha * B
    uniform = np.ones(n) / n
    score_norm = s / s.sum()
    p_explore = lambda_uniform * uniform + (1 - lambda_uniform) * score_norm
    p_explore = p_explore / p_explore.sum()
    b_explore = B_explore * p_explore

    # Exploitation part
    B_exploit = (1 - alpha) * B
    w_exploit = (s ** gamma)
    w_exploit = w_exploit / w_exploit.sum()
    b_exploit = B_exploit * w_exploit

    b_total = b_explore + b_exploit

    # Apply optional floor/cap
    if b_floor > 0 or np.isfinite(b_cap):
        b_total = apply_floor_cap_proportionally(b_total, B, b_min=b_floor, b_max=b_cap)

        # If we enforce caps/floors we lose the exact decomposition; recompute a best-effort split
        # by scaling explore/exploit parts proportionally to match final totals:
        scale = b_total / (b_explore + b_exploit + 1e-18)
        b_explore = b_explore * scale
        b_exploit = b_exploit * scale

    out["b_explore"] = b_explore
    out["b_exploit"] = b_exploit
    out["b_total"] = b_total

    if not add_columns:
        return out[["authorID", "b_total"]].copy()

    return out

