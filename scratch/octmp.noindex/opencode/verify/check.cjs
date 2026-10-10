const { Board } = require('./connect.cjs');

const cases = [
  [['. . . . .', ' . . . . .', '  . . . . .', '   . . . . .', '    . . . . .']],
  [['X']],
  [['O']],
  [['O O O X', ' X . . X', '  X . . X', '   X O O O']],
  [['X O . .', ' O X X X', '  O X O .', '   . O X .', '    X X O O']],
  [['X . . .', ' . X O .', '  O . X O', '   . O . X', '    . . O .']],
  [['. O . .', ' O X X X', '  O X O .', '   X X O X', '    . O X .']],
  [['. O . .', ' O X X X', '  O O O .', '   X X O X', '    . O X .']],
  [['. X X . .', ' X . X . X', '  . X . X .', '   . X X . .', '    O O O O O']],
  [['O X X X X X X X X', ' O X O O O O O O O', '  O X O X X X X X O', '   O X O X O O O X O', '    O X O X X X O X O', '     O X O O O X O X O', '      O X X X X X O X O', '       O O O O O O O X O', '        X X X X X X X X O']],
];

const expected = ['', 'X', 'O', '', '', '', 'X', 'O', 'X', 'X'];

let failed = 0;
cases.forEach((board, i) => {
  const got = new Board(board).winner();
  const ok = got === expected[i];
  if (!ok) failed++;
  console.log(`${ok ? 'PASS' : 'FAIL'} case ${i + 1}: expected ${JSON.stringify(expected[i])}, got ${JSON.stringify(got)}`);
});
process.exit(failed ? 1 : 0);
