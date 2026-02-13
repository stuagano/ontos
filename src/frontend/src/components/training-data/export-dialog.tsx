import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { ExportRequest, ExportFormat } from '@/types/training-data';
import { Loader2, Download, FileJson, FileText, Database } from 'lucide-react';

const exportFormSchema = z.object({
  format: z.nativeEnum(ExportFormat),
  include_splits: z.array(z.string()).default(['train', 'val', 'test']),
  only_approved: z.boolean().default(true),
  include_metadata: z.boolean().default(false),
  output_path: z.string().optional(),
});

type ExportFormValues = z.infer<typeof exportFormSchema>;

const formatDescriptions: Record<ExportFormat, { icon: React.ReactNode; description: string }> = {
  [ExportFormat.JSONL]: {
    icon: <FileJson className="h-4 w-4" />,
    description: 'OpenAI chat format, one conversation per line',
  },
  [ExportFormat.ALPACA]: {
    icon: <FileJson className="h-4 w-4" />,
    description: 'Instruction-input-output format for fine-tuning',
  },
  [ExportFormat.SHAREGPT]: {
    icon: <FileJson className="h-4 w-4" />,
    description: 'ShareGPT conversation format',
  },
  [ExportFormat.PARQUET]: {
    icon: <Database className="h-4 w-4" />,
    description: 'Columnar format for large-scale processing',
  },
  [ExportFormat.CSV]: {
    icon: <FileText className="h-4 w-4" />,
    description: 'Simple tabular format',
  },
};

interface ExportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collectionId: string;
  onExport: (request: ExportRequest) => Promise<void>;
}

export default function ExportDialog({
  open,
  onOpenChange,
  collectionId,
  onExport,
}: ExportDialogProps) {
  const [isExporting, setIsExporting] = React.useState(false);

  const form = useForm<ExportFormValues>({
    resolver: zodResolver(exportFormSchema),
    defaultValues: {
      format: ExportFormat.JSONL,
      include_splits: ['train', 'val', 'test'],
      only_approved: true,
      include_metadata: false,
      output_path: '',
    },
  });

  const selectedFormat = form.watch('format');

  const onSubmit = async (values: ExportFormValues) => {
    setIsExporting(true);
    try {
      const request: ExportRequest = {
        collection_id: collectionId,
        format: values.format,
        include_splits: values.include_splits.length > 0 ? values.include_splits : undefined,
        only_approved: values.only_approved,
        include_metadata: values.include_metadata,
        output_path: values.output_path || undefined,
      };
      await onExport(request);
    } finally {
      setIsExporting(false);
    }
  };

  const toggleSplit = (split: string, currentSplits: string[]) => {
    if (currentSplits.includes(split)) {
      return currentSplits.filter(s => s !== split);
    } else {
      return [...currentSplits, split];
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="h-5 w-5" />
            Export Training Data
          </DialogTitle>
          <DialogDescription>
            Export QA pairs in various formats for model fine-tuning.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="format"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Export Format</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select format" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {Object.entries(formatDescriptions).map(([format, { icon, description }]) => (
                        <SelectItem key={format} value={format}>
                          <div className="flex items-center gap-2">
                            {icon}
                            <span className="uppercase">{format}</span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {selectedFormat && (
                    <FormDescription>
                      {formatDescriptions[selectedFormat].description}
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="include_splits"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Include Splits</FormLabel>
                  <div className="flex gap-4">
                    {['train', 'val', 'test'].map((split) => (
                      <label key={split} className="flex items-center gap-2 cursor-pointer">
                        <Checkbox
                          checked={field.value.includes(split)}
                          onCheckedChange={() => {
                            field.onChange(toggleSplit(split, field.value));
                          }}
                        />
                        <span className="capitalize">{split}</span>
                      </label>
                    ))}
                  </div>
                  <FormDescription>
                    Select which data splits to include in the export
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="only_approved"
              render={({ field }) => (
                <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <div className="space-y-1 leading-none">
                    <FormLabel>Only approved pairs</FormLabel>
                    <FormDescription>
                      Only export pairs with approved status
                    </FormDescription>
                  </div>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="include_metadata"
              render={({ field }) => (
                <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <div className="space-y-1 leading-none">
                    <FormLabel>Include metadata</FormLabel>
                    <FormDescription>
                      Include quality scores, flags, and lineage info
                    </FormDescription>
                  </div>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="output_path"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Output Path (optional)</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="e.g., /Volumes/catalog/schema/volume/exports/"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    Unity Catalog volume path for output. Leave empty for default location.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isExporting}>
                {isExporting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Exporting...
                  </>
                ) : (
                  <>
                    <Download className="mr-2 h-4 w-4" />
                    Export
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
