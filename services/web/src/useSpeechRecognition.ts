import { useCallback, useEffect, useRef, useState } from "react";

type SpeechRecognitionResultLike = {
  0: { transcript: string };
  isFinal: boolean;
};

type SpeechRecognitionResultEventLike = Event & {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: SpeechRecognitionResultLike;
  };
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null;
  onstart: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

const ERROR_MESSAGES: Record<string, string> = {
  "audio-capture": "No microphone was found.",
  "not-allowed": "Microphone access was denied.",
  network: "Voice recognition could not reach the browser service.",
  "no-speech": "No speech was detected.",
};

const RESTART_DELAY_MS = 100;

function getSpeechRecognitionConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

export function useSpeechRecognition(language = "en-US") {
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const shouldKeepListeningRef = useRef(false);
  const restartTimeoutRef = useRef<number | null>(null);
  const finalTranscriptRef = useRef("");
  const interimTranscriptRef = useRef("");
  const [isSupported] = useState(
    () => getSpeechRecognitionConstructor() !== null,
  );
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (recognitionRef.current) recognitionRef.current.lang = language;
  }, [language]);

  useEffect(() => {
    return () => {
      shouldKeepListeningRef.current = false;
      if (restartTimeoutRef.current !== null) {
        window.clearTimeout(restartTimeoutRef.current);
      }
      recognitionRef.current?.stop();
    };
  }, []);

  const start = useCallback(() => {
    const SpeechRecognition = getSpeechRecognitionConstructor();
    if (!SpeechRecognition) return;

    if (!recognitionRef.current) {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = language;
      recognition.onstart = () => {
        setIsListening(true);
        setError(null);
      };
      recognition.onend = () => {
        setIsListening(false);
        if (!shouldKeepListeningRef.current) return;
        restartTimeoutRef.current = window.setTimeout(() => {
          if (!shouldKeepListeningRef.current) return;
          try {
            recognition.start();
          } catch {
            setError("Voice input is already starting.");
          }
        }, RESTART_DELAY_MS);
      };
      recognition.onerror = (event) => {
        setIsListening(false);
        setError(ERROR_MESSAGES[event.error] ?? "Voice input failed.");
        if (event.error !== "no-speech") {
          shouldKeepListeningRef.current = false;
        }
      };
      recognition.onresult = (event) => {
        let nextInterimTranscript = "";
        for (let index = event.resultIndex; index < event.results.length; index++) {
          const result = event.results[index];
          if (result.isFinal) {
            finalTranscriptRef.current += `${result[0].transcript} `;
          } else {
            nextInterimTranscript += `${result[0].transcript} `;
          }
        }
        interimTranscriptRef.current = nextInterimTranscript;
        setTranscript(
          `${finalTranscriptRef.current}${interimTranscriptRef.current}`.trim(),
        );
      };
      recognitionRef.current = recognition;
    }

    shouldKeepListeningRef.current = true;
    setError(null);
    finalTranscriptRef.current = "";
    interimTranscriptRef.current = "";
    setTranscript("");
    try {
      recognitionRef.current.start();
    } catch {
      setError("Voice input is already starting.");
    }
  }, [language]);

  const stop = useCallback(() => {
    shouldKeepListeningRef.current = false;
    if (restartTimeoutRef.current !== null) {
      window.clearTimeout(restartTimeoutRef.current);
      restartTimeoutRef.current = null;
    }
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  return { error, isListening, isSupported, start, stop, transcript };
}
