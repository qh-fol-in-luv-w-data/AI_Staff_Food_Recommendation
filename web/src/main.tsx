import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./fonts.css";
import "./styles.css";
import App from "./App";
import Gallery from "./Gallery";

const gallery = new URLSearchParams(location.search).has("gallery");

createRoot(document.getElementById("root")!).render(<StrictMode>{gallery ? <Gallery /> : <App />}</StrictMode>);
