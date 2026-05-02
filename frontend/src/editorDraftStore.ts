import type { DraftDocument, DraftDocumentPayload } from "./types";

type Listener = () => void;

let activeDraftPayload: DraftDocumentPayload | null = null;
let activeDraftDocument: DraftDocument | null = null;
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((listener) => listener());
}

export const editorDraftStore = {
  getSnapshot: () => ({ payload: activeDraftPayload, document: activeDraftDocument }),
  subscribe: (listener: Listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  openPayload: (payload: DraftDocumentPayload) => {
    activeDraftPayload = payload;
    activeDraftDocument = null;
    notify();
  },
  setDocument: (document: DraftDocument | null) => {
    activeDraftDocument = document;
    notify();
  },
  close: () => {
    activeDraftPayload = null;
    activeDraftDocument = null;
    notify();
  },
};
