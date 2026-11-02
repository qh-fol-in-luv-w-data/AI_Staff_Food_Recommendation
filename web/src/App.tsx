import { domMax, LazyMotion, MotionConfig } from "motion/react";
import { Assistant } from "./components/Assistant";
import { DishDetail } from "./components/DishDetail";
import { Menu } from "./components/Menu";
import { ConfirmSheet, PaymentSheet, Success } from "./components/Sheets";
import { Attract, FlyLayer, Offline, TopBar } from "./components/Stage";
import { Tray } from "./components/Tray";
import { liteMode } from "./lib/format";
import { KioskProvider, useKiosk } from "./store";

function Shell() {
  const { started } = useKiosk();
  return (
    <div className="app" data-started={started} data-lite={liteMode() || undefined}>
      <TopBar />
      <main className="stage" inert={!started}>
        <Assistant />
        <Menu />
        <Tray />
      </main>
      <Attract />
      <DishDetail />
      <ConfirmSheet />
      <PaymentSheet />
      <Success />
      <FlyLayer />
      <Offline />
    </div>
  );
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domMax} strict>
        <KioskProvider>
          <Shell />
        </KioskProvider>
      </LazyMotion>
    </MotionConfig>
  );
}
