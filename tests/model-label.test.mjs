import {test} from 'node:test';
import assert from 'node:assert/strict';
import {modelLabel} from '../src/model-label.ts';
test('show seed and checkpoint first, including guarded distinction',()=>{
 assert.equal(modelLabel('server-mixed-21x21-reviewed/seed_3/best_guarded.zip'),'S3 · best_guarded.zip · mixed-21x21-reviewed');
 assert.notEqual(modelLabel('server-mixed-21x21-reviewed/seed_3/best.zip'),modelLabel('server-mixed-21x21-reviewed/seed_3/best_guarded.zip'));
});
test('retain intermediate checkpoint path and handle runs without seeds',()=>{
 assert.equal(modelLabel('server-mixed/seed_2/checkpoints/ppo_100_steps.zip'),'S2 · checkpoints/ppo_100_steps.zip · mixed');
 assert.equal(modelLabel('smoke/final.zip'),'final.zip · smoke');
});
