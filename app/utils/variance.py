"""
Variance calculation utility.
Mirrors the existing calcShift() logic from the original index.html.
"""
from decimal import Decimal, ROUND_HALF_UP


def calculate_shift(
    open_n1: float, open_n2: float, open_n3: float, open_n4: float,
    close_n1: float, close_n2: float, close_n3: float, close_n4: float,
    hsd_price: float, ms_price: float,
    cash: float = 0, upi: float = 0, pine: float = 0, otp: float = 0,
    credit_given: float = 0, expenses: float = 0,
    testing_amt: float = 0, bp_rewards: float = 0,
    test_hsd: float = 0, test_ms: float = 0,
    open_hsd: float = 0, load_hsd: float = 0,
    open_ms: float = 0, load_ms: float = 0,
) -> dict:
    """
    Calculate all shift metrics from raw Vtot readings and collection data.

    This is a direct port of the JavaScript calcShift() function from the
    existing index.html, preserving all business logic exactly.

    Returns a dict with all computed values:
      hsd_sold, ms_sold, hsd_net, ms_net,
      hsd_sales, ms_sales, total_sales,
      gross, net, variance, variance_status,
      cash_in_hand, close_hsd, close_ms
    """
    # Litres sold from Vtot readings
    hsd_sold = (close_n1 - open_n1) + (close_n2 - open_n2)
    ms_sold = (close_n3 - open_n3) + (close_n4 - open_n4)

    # Net litres after testing deduction
    hsd_net = hsd_sold - test_hsd
    ms_net = ms_sold - test_ms

    # Sales calculation
    hsd_sales = hsd_net * hsd_price
    ms_sales = ms_net * ms_price
    total_sales = hsd_sales + ms_sales

    # Total Accounted Collection
    # Cash here represents cash-in-hand brought to the manager.
    # We add back the expenses and bp_rewards to see the total value generated.
    gross = cash + upi + pine + otp + credit_given + expenses + bp_rewards + testing_amt
    net_collected = cash + upi + pine + otp + credit_given # Without non-cash deductions

    # Variance: totalSales - totalAccounted
    variance = total_sales - gross

    # Status determination (matches existing logic exactly)
    if abs(variance) < 1:
        variance_status = "PERFECT"
    elif variance > 0:
        variance_status = "SHORTAGE"
    else:
        variance_status = "EXCESS"

    # Cash in hand before any manager adjustment (already represents what the DSM gives)
    cash_in_hand = cash

    # Closing stock
    close_hsd = open_hsd + load_hsd - hsd_net
    close_ms = open_ms + load_ms - ms_net

    return {
        "hsd_sold": round(hsd_sold, 3),
        "ms_sold": round(ms_sold, 3),
        "hsd_net": round(hsd_net, 3),
        "ms_net": round(ms_net, 3),
        "hsd_sales": round(hsd_sales, 2),
        "ms_sales": round(ms_sales, 2),
        "total_sales": round(total_sales, 2),
        "expected_sales": round(total_sales, 2),
        "gross_collected": round(gross, 2),
        "net_collected": round(net_collected, 2),
        "variance": round(variance, 2),
        "variance_status": variance_status,
        "cash_in_hand": round(cash_in_hand, 2),
        "close_hsd": round(close_hsd, 2),
        "close_ms": round(close_ms, 2),
    }


def validate_closing_readings(
    open_n1: float, open_n2: float, open_n3: float, open_n4: float,
    close_n1: float, close_n2: float, close_n3: float, close_n4: float,
) -> dict:
    """
    Validate that closing Vtot values are >= opening values.
    Returns {"valid": bool, "errors": list[str]}
    """
    errors = []
    if close_n1 < open_n1:
        errors.append("N1 closing cannot be less than opening")
    if close_n2 < open_n2:
        errors.append("N2 closing cannot be less than opening")
    if close_n3 < open_n3:
        errors.append("N3 closing cannot be less than opening")
    if close_n4 < open_n4:
        errors.append("N4 closing cannot be less than opening")
    if not close_n1 or not close_n2 or not close_n3 or not close_n4:
        errors.append("All closing values are required")

    return {"valid": len(errors) == 0, "errors": errors}


def check_mismatch_alert(variance: float, threshold: float = 100.0) -> dict:
    """
    Check if variance exceeds the mismatch threshold.
    Returns alert details if it does.
    """
    if abs(variance) > threshold:
        return {
            "alert": True,
            "type": "SHORTAGE" if variance > 0 else "EXCESS",
            "amount": abs(variance),
            "message": f"Variance of ₹{abs(variance):.2f} exceeds threshold of ₹{threshold:.2f}",
        }
    return {"alert": False}
