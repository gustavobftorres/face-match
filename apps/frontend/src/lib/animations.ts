import { Transition, Variants } from "framer-motion";

export const springs = {
  snappy: {
    type: "spring",
    stiffness: 420,
    damping: 26,
    mass: 0.7,
  } satisfies Transition,
  bouncy: {
    type: "spring",
    stiffness: 340,
    damping: 16,
    mass: 0.8,
  } satisfies Transition,
  gentle: {
    type: "spring",
    stiffness: 200,
    damping: 22,
    mass: 1,
  } satisfies Transition,
  buttonPress: {
    type: "spring",
    stiffness: 550,
    damping: 22,
    mass: 0.5,
  } satisfies Transition,
  modalOpen: {
    type: "spring",
    stiffness: 320,
    damping: 26,
    mass: 0.85,
  } satisfies Transition,
  tabIndicator: {
    type: "spring",
    stiffness: 460,
    damping: 32,
  } satisfies Transition,
} as const;

export const easings = {
  smoothOut: [0.22, 1, 0.36, 1] as const,
};

export const fadeInUp: Variants = {
  hidden: {
    opacity: 0,
    y: 16,
  },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.38,
      ease: easings.smoothOut,
    },
  },
  exit: {
    opacity: 0,
    y: -10,
    transition: {
      duration: 0.2,
    },
  },
};

export const scaleInPop: Variants = {
  hidden: {
    opacity: 0,
    scale: 0.92,
  },
  visible: {
    opacity: 1,
    scale: 1,
    transition: springs.snappy,
  },
  exit: {
    opacity: 0,
    scale: 0.94,
    transition: {
      duration: 0.16,
    },
  },
};

export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.07,
      delayChildren: 0.05,
    },
  },
};

export const staggerFastContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.045,
      delayChildren: 0.03,
    },
  },
};

export const staggerItem: Variants = {
  hidden: {
    opacity: 0,
    y: 18,
    scale: 0.97,
  },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: springs.snappy,
  },
};

export const modalBackdrop: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.22 },
  },
  exit: {
    opacity: 0,
    transition: { duration: 0.18 },
  },
};

export const modalSheet: Variants = {
  hidden: {
    opacity: 0,
    y: 36,
    scale: 0.96,
  },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: springs.modalOpen,
  },
  exit: {
    opacity: 0,
    y: 28,
    scale: 0.96,
    transition: { duration: 0.18 },
  },
};
