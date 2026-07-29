import React, { useState } from "react";
import { CheckSquare, AlertTriangle, Check, RefreshCw, Eye } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

export function ReviewQueue() {
  const [items, setItems] = useState([
    {
      id: "rev_1",
      pageNumber: 4,
      epicId: "TN/04/132/084912",
      extractedName: "முருகன் (Murugan)",
      confidence: 0.62,
      field: "Tamil Name",
      status: "pending",
    },
    {
      id: "rev_2",
      pageNumber: 7,
      epicId: "TN/04/132/091244",
      extractedName: "கவிதா (Kavitha)",
      confidence: 0.58,
      field: "House No.",
      status: "pending",
    },
  ]);

  const handleVerify = (id: string) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, status: "verified" } : item)));
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-background animate-fade-slide">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <CheckSquare className="w-6 h-6 text-amber-500" />
            <span>Low-Confidence Verification Queue</span>
          </h1>
          <p className="text-xs text-muted-foreground">
            Manually verify and correct OCR fields detected below 70% confidence.
          </p>
        </div>

        <Badge variant="amber">{items.filter((i) => i.status === "pending").length} Pending Verification</Badge>
      </div>

      {/* Item List */}
      <div className="space-y-4">
        {items.map((item) => (
          <Card key={item.id} className="p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border-amber-500/20">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-xl bg-amber-500/10 text-amber-500 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="epic-chip">{item.epicId}</span>
                  <Badge variant="rose">Confidence: {(item.confidence * 100).toFixed(0)}%</Badge>
                  <span className="text-xs text-muted-foreground">• Page {item.pageNumber}</span>
                </div>
                <h4 className="text-base font-bold text-foreground">{item.extractedName}</h4>
                <p className="text-xs text-muted-foreground">Flagged field: <span className="font-semibold text-foreground">{item.field}</span></p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {item.status === "verified" ? (
                <Badge variant="emerald" className="px-3 py-1 text-xs">
                  <Check className="w-3.5 h-3.5" /> Verified
                </Badge>
              ) : (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
                  >
                    Re-crop
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => handleVerify(item.id)}
                    leftIcon={<Check className="w-3.5 h-3.5" />}
                  >
                    Approve
                  </Button>
                </>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
