import { useEffect, useState } from "react";
import { api, call } from "../lib/api/client";

/** Polls /api/status; shows a banner when the marketplace MCP server (or GigSim behind it) is unreachable. */
export default function DegradedBanner() {
  const [st, setSt] = useState<any>(null);
  useEffect(() => {
    let alive = true;
    const tick = () => call(api.GET("/api/status")).then((d) => alive && setSt(d)).catch(() => alive && setSt({ marketplace: "unavailable" }));
    tick();
    const id = setInterval(tick, 8000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  if (!st || st.marketplace === "ok") return null;
  return (
    <div className="banner bad" role="alert" data-testid="degraded-banner">
      Marketplace unavailable. GigBid has queued your work ({st.queued_jobs ?? 0} jobs) and will retry automatically when it is back.
      Nothing has been sent.
    </div>
  );
}
