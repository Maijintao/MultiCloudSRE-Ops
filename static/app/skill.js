// Compatibility shim for clients that saw a stale singular module path during
// the native ES module migration. New code imports ./skills.js directly.
export {
  currentSkills,
  nextSkillName,
  formatBytes,
  renderSkillManagerSection,
  bindSkillManager,
} from "./skills.js";
