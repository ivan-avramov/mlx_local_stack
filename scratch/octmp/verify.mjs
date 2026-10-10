import { solve } from '$STACK_WORKDIR/scratch/octmp/oc-alphametics-1b86flt1/alphametics/alphametics.js';

const cases = [
  ['I + BB == ILL', { I: 1, B: 9, L: 0 }],
  ['A == B', null],
  ['ACA + DD == BD', null],
  ['AS + A == MOM', { A: 9, S: 2, M: 1, O: 0 }],
  ['NO + NO + TOO == LATE', { N: 7, O: 4, T: 9, L: 1, A: 0, E: 2 }],
  ['HE + SEES + THE == LIGHT', { E: 4, G: 2, H: 5, I: 0, L: 1, S: 9, T: 7 }],
  ['SEND + MORE == MONEY', { S: 9, E: 5, N: 6, D: 7, M: 1, O: 0, R: 8, Y: 2 }],
  ['AND + A + STRONG + OFFENSE + AS + A + GOOD == DEFENSE', { A: 5, D: 3, E: 4, F: 7, G: 8, N: 0, O: 2, R: 1, S: 6, T: 9 }],
  ['THIS + A + FIRE + THEREFORE + FOR + ALL + HISTORIES + I + TELL + A + TALE + THAT + FALSIFIES + ITS + TITLE + TIS + A + LIE + THE + TALE + OF + THE + LAST + FIRE + HORSES + LATE + AFTER + THE + FIRST + FATHERS + FORESEE + THE + HORRORS + THE + LAST + FREE + TROLL + TERRIFIES + THE + HORSES + OF + FIRE + THE + TROLL + RESTS + AT + THE + HOLE + OF + LOSSES + IT + IS + THERE + THAT + SHE + STORES + ROLES + OF + LEATHERS + AFTER + SHE + SATISFIES + HER + HATE + OFF + THOSE + FEARS + A + TASTE + RISES + AS + SHE + HEARS + THE + LEAST + FAR + HORSE + THOSE + FAST + HORSES + THAT + FIRST + HEAR + THE + TROLL + FLEE + OFF + TO + THE + FOREST + THE + HORSES + THAT + ALERTS + RAISE + THE + STARES + OF + THE + OTHERS + AS + THE + TROLL + ASSAILS + AT + THE + TOTAL + SHIFT + HER + TEETH + TEAR + HOOF + OFF + TORSO + AS + THE + LAST + HORSE + FORFEITS + ITS + LIFE + THE + FIRST + FATHERS + HEAR + OF + THE + HORRORS + THEIR + FEARS + THAT + THE + FIRES + FOR + THEIR + FEASTS + ARREST + AS + THE + FIRST + FATHERS + RESETTLE + THE + LAST + OF + THE + FIRE + HORSES + THE + LAST + TROLL + HARASSES + THE + FOREST + HEART + FREE + AT + LAST + OF + THE + LAST + TROLL + ALL + OFFER + THEIR + FIRE + HEAT + TO + THE + ASSISTERS + FAR + OFF + THE + TROLL + FASTS + ITS + LIFE + SHORTER + AS + STARS + RISE + THE + HORSES + REST + SAFE + AFTER + ALL + SHARE + HOT + FISH + AS + THEIR + AFFILIATES + TAILOR + A + ROOFS + FOR + THEIR + SAFE == FORTRESSES', { A: 1, E: 0, F: 5, H: 8, I: 7, L: 2, O: 6, R: 3, S: 4, T: 9 }],
];

const eq = (a, b) => {
  if (a === null || b === null) return a === b;
  const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
  if (ka.length !== kb.length || ka.some((k, i) => k !== kb[i] || a[k] !== b[k])) return false;
  return true;
};

let fail = 0;
for (const [puzzle, expected] of cases) {
  const t0 = Date.now();
  const got = solve(puzzle);
  const ms = Date.now() - t0;
  const ok = eq(got, expected);
  if (!ok) fail++;
  console.log(`${ok ? 'PASS' : 'FAIL'} (${ms}ms) ${puzzle.slice(0, 40)}...  got=${JSON.stringify(got)}`);
}
process.exit(fail ? 1 : 0);
