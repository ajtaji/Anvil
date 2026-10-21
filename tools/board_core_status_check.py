"""Host-only regression for latched failures in model-run core status."""
from unittest.mock import patch
import board_model_run as model


def check(reply, fails, error=None):
    with patch.object(model, "command", return_value=reply):
        status = model.coretest(None)
    if error is not None:
        assert status["error"] == error, status
    try:
        model.require_coretest_healthy(status)
    except model.RunFailed:
        assert fails, status
    else:
        assert not fails, status


check("coretest started=0 stopped=0 runs=0 nonce=12 error=0\npmf>", False, 0)
check("coretest started=1 stopped=0 runs=0 nonce=13 error=-20\n"
      "Failure latched. No re-release or warm rejoin.\npmf>", True, -20)
check("coretest started=0 stopped=0 runs=0 nonce=14 error=3\npmf>", True, 3)
check("coretest started=1 stopped=0 runs=0 nonce=15 error=invalid\npmf>", True)
print("PASS: healthy, negative timeout, positive fault and malformed core status")
