import { Fragment } from "react";

import { cn } from "@/lib/utils";

/**
 * One highlighted phrase inside a translated sentence.
 *
 * The obvious way to colour a word in a heading is to split the string in
 * three and translate the pieces. That works in English and falls apart
 * everywhere else: Hindi puts the verb last, Urdu runs the other way, and
 * Tamil may not have a separate word there at all. Three fragments assembled
 * in English order produce nonsense in half our languages.
 *
 * So the emphasis travels inside the string, marked with asterisks, and the
 * translator decides which words carry it:
 *
 *   en: "Find the schemes you *actually* qualify for"
 *   hi: "उन योजनाओं को खोजें जिनके लिए आप *वाकई* पात्र हैं"
 *
 * A string with no asterisks renders as plain text, so this is safe to use on
 * every locale whether or not it has adopted the convention.
 */
export function Marked({
  text,
  className,
  markClassName = "text-leaf",
}: {
  text: string;
  className?: string;
  markClassName?: string;
}) {
  const parts = text.split("*");
  return (
    <span className={className}>
      {parts.map((part, index) =>
        // Odd indices are the runs that sat between a pair of asterisks.
        index % 2 === 1 ? (
          <em key={index} className={cn("not-italic", markClassName)}>
            {part}
          </em>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </span>
  );
}
