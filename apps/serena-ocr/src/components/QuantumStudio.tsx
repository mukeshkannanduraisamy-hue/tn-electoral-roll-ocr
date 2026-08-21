"use client";

import React from "react";
import { QuantumPartMatrix } from "./QuantumPartMatrix";
import { QuantumDocumentStage } from "./QuantumDocumentStage";
import { QuantumElectorStream } from "./QuantumElectorStream";
import { QuantumTelemetryDock } from "./QuantumTelemetryDock";

export const QuantumStudio: React.FC = () => {
  return (
    <main className="flex-1 flex flex-col overflow-hidden p-4 sm:p-5 gap-4 min-h-0 min-w-0 bg-transparent">
      {/* 3-Column Studio Workspace */}
      <div className="flex-1 flex flex-row gap-4 min-h-0 min-w-0 overflow-hidden">
        {/* Left Rail: Part Matrix & Folder Navigator */}
        <QuantumPartMatrix />

        {/* Center Stage: Interactive Visual Sheet & Neural Raycast Scanner */}
        <QuantumDocumentStage />

        {/* Right Dock: Live Curated Elector Vault Stream */}
        <QuantumElectorStream />
      </div>

      {/* Bottom Telemetry Dock */}
      <QuantumTelemetryDock />
    </main>
  );
};
